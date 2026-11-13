"""Shared Python interface used by both the CLI and HTTP adapter."""

import json
from datetime import date
from uuid import uuid4

import openai
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage, messages_from_dict, messages_to_dict
from langgraph.errors import GraphRecursionError

import answer_check
import evidence_refs
import rules
import watches
from action_tools import action_context
from actions import ActionNotFoundError, ActionStore
from llm import PROMPT_VERSION, build_agent
from order_selection import selection_context
from plan_context import plan_context

# Cap on raw CSV rows returned with one answer (a full order list cites all 120).
MAX_EVIDENCE_ROWS = 200


STATUS_WORDS = {'PROPOSED': 'waiting for Confirm', 'EXECUTED': 'confirmed and saved',
                'CANCELLED': 'cancelled', 'EXPIRED': 'expired unconfirmed'}


def today_note(actions=None, session_id=None):
    """Today's data date and the current state of this conversation's proposals; sent with each turn,
    never saved in the history. Proposal cards in the history show the state at creation, and the
    manager may have confirmed or cancelled them since (evaluation Q32)."""
    day = rules.today_iso()
    loaded = ('the course data' if rules.current_version() == 'v0'
              else f'scripted snapshot {rules.current_version()}, simulated data, not real events')
    return SystemMessage(content=f'Today is {date.fromisoformat(day):%A} {day}, the date of the data loaded ({loaded}). '
                                 'Use it for every business fact; reminders still use the real calendar.'
                                 + _proposal_states(actions, session_id),
                         name='data_date')


def _proposal_states(actions, session_id):
    if actions is None or session_id is None:
        return ''
    proposals = actions.list_proposals(session_id=session_id, limit=10)
    if not proposals:
        return ''
    lines = [f"{p['id']} ({p['summary']}): {STATUS_WORDS.get(p['status'], p['status'].lower())}" for p in proposals]
    return ('\nCurrent state of the proposals in this conversation (newer than any card in the history): '
            + '; '.join(lines) + '.')


def _saved(messages):
    return [m for m in messages if not (m.type == 'system' and getattr(m, 'name', None) == 'data_date')]


class AgentIncompleteError(RuntimeError):
    """The agent stopped without a final answer (step limit, unanswered tool call, empty reply)."""


class ModelUnavailableError(RuntimeError):
    """The language-model API could not be used; the message says why in plain words."""


def _model_problem(exc):
    if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)):
        return 'The model API rejected the API key. Check the key in backend/.env.'
    if isinstance(exc, openai.RateLimitError):
        return 'The model API is rate-limited or out of quota. Try again later.'
    if isinstance(exc, openai.APIConnectionError):
        return 'Cannot reach the model API. Check the network connection.'
    if isinstance(exc, (openai.NotFoundError, openai.BadRequestError)):
        return 'The model API rejected the request. Check the model name and settings.'
    return 'The model API returned an error.'


def _result(message):
    try:
        value = json.loads(message.content)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def tool_results(messages):
    """The parsed results of every tool call in one turn."""
    return [_result(m) for m in messages if m.type == 'tool']


def checked(answer, messages, question, earlier=()):
    """Which order IDs, dates and figures in the answer the turn's tool results do not contain."""
    return answer_check.check(answer, tool_results(messages), question, rules.today_iso(), tool_results(earlier))


RETRY_NOTE = ('Your last draft stated figures or order IDs without looking anything up in this turn. Figures '
              'must come from a fresh tool call, never from earlier turns: call the matching tool now, then '
              'answer again.')


ATTRIBUTION_NOTE = ('Your last draft gave an order an overdue figure that is not its own ({items}). Each order\'s '
                    'overdue days are in its own record (overdue_calendar_days, risk_reasons): look them up again '
                    'and answer again.')


def misattributed(answer, messages, question, earlier):
    """Overdue figures the answer attaches to the wrong order, e.g. 'ORD-107: 9 days overdue'."""
    return [item['text'] for item in checked(answer, messages, question, earlier)['unverified']
            if item['kind'] == 'attribution']


def needs_lookup(answer, messages, question, earlier):
    """An answer that states unverified figures while calling no tool at all is answered again once."""
    if any(m.type == 'tool' for m in messages):
        return False
    return bool(checked(answer, messages, question, earlier)['unverified'])


def turn_details(messages, actions=None, *, include_evidence=True):
    """What one turn did: tool calls in order, the CSV rows its tools cited, and any proposals."""
    calls, by_id, results = [], {}, []
    for message in messages:
        if message.type == 'ai':
            for call in getattr(message, 'tool_calls', None) or []:
                entry = {'name': call['name'], 'arguments': call.get('args') or {}, 'status': None}
                calls.append(entry)
                by_id[call.get('id')] = entry
        elif message.type == 'tool':
            result = _result(message)
            if getattr(message, 'tool_call_id', None) in by_id:
                by_id[message.tool_call_id]['status'] = result.get('status')
                by_id[message.tool_call_id]['result'] = result
            results.append(result)
    refs = evidence_refs.collect(results, versioned=include_evidence, resolve_implicit=include_evidence)
    proposals = []
    for result in results:
        if result.get('status') == 'proposed' and isinstance(result.get('proposal'), dict):
            try:
                proposals.append(actions.get(result['proposal']['id']) if actions else result['proposal'])
            except ActionNotFoundError:
                continue
    evidence = {'refs': refs, 'rows': {}, 'source_context': 'legacy_unknown',
                'warnings': ['Historical data version was not recorded; original tool outputs are available '
                             'but current CSV rows are not substituted.']}
    if include_evidence:
        evidence = {'refs': refs, 'rows': evidence_refs.raw_rows(refs[:MAX_EVIDENCE_ROWS]),
                    'data_version': rules.current_version(), 'data_date': rules.today_iso(),
                    'source_context': 'recorded_snapshot', 'warnings': []}
    return {'tool_calls': calls, 'evidence': evidence, 'proposals': proposals}


def _record_turn(final_message, messages, question, earlier=(), retried=False):
    """Keep the answer's actual evidence rows and check, rather than rebuilding them later.

    response_metadata is persisted by LangChain message serialization, but is not
    model content. Historical tool results already hold each original structured result.
    """
    evidence = turn_details(messages)['evidence']
    check = {**checked(final_message.content, messages, question, earlier), 'retried': retried}
    final_message.response_metadata['manager_copilot'] = {
        'data_version': rules.current_version(), 'data_date': rules.today_iso(),
        'evidence': evidence, 'answer_check': check,
    }
    return evidence, check


class ChatService:
    def __init__(self, store, config=None, agent=None):
        self.store = store
        self.actions = ActionStore(store)
        self.actions.setup()
        self.agent = agent if agent is not None else build_agent(config)

    def create_session(self, title='New conversation', request_id=None):
        return self.store.create_session(title, request_id)

    def list_sessions(self):
        return self.store.list_sessions()

    def get_history(self, session_id):
        """Questions and answers; each answer that used tools carries its evidence and proposals."""
        messages = messages_from_dict(self.store.get_history(session_id))
        history, turn, question, earlier = [], [], '', []
        for message in messages:
            if message.type == 'human':
                earlier += turn
                turn, question = [], message.content
                if message.content:
                    history.append({'role': 'human', 'content': message.content})
                continue
            turn.append(message)
            if message.type == 'ai' and message.content and not getattr(message, 'tool_calls', None):
                item = {'role': 'ai', 'content': message.content}
                details = turn_details(turn, self.actions, include_evidence=False)
                saved_context = message.response_metadata.get('manager_copilot', {})
                if not isinstance(saved_context, dict):
                    saved_context = {}
                if isinstance(saved_context.get('evidence'), dict):
                    details['evidence'] = saved_context['evidence']
                if details['tool_calls']:
                    item.update(details)
                item['answer_check'] = saved_context.get('answer_check',
                    {'checked': 0, 'unverified': [], 'retried': False, 'unavailable': True})
                history.append(item)
        return history

    def send_message(self, session_id, message, request_id=None):
        if not isinstance(message, str) or not message.strip() or len(message) > 20000:
            raise ValueError('Message must contain 1 to 20000 characters.')
        turn_id = str(uuid4())
        question = message.strip()
        claim = self.store.claim_chat_request(session_id, request_id, question, turn_id)
        if claim is not None and 'response' in claim:
            # Replay the original answer and its frozen evidence, but show each card's
            # current state just as get_history does after confirmation or cancellation.
            response = claim['response']
            proposals = []
            for proposal in response.get('proposals', []):
                try:
                    proposals.append(self.actions.get(proposal['id']))
                except ActionNotFoundError:
                    continue
            return {**response, 'proposals': proposals}
        try:
            with self.store.keep_chat_request_alive(claim):
                if claim is not None and claim.get('abandoned_turn'):
                    self.actions.fail_turn(claim['abandoned_turn'])
                return self._generate_message(session_id, question, turn_id, claim)
        except BaseException:
            try:
                self.actions.fail_turn(turn_id)
            finally:
                self.store.fail_chat_request(claim)
            raise

    def _generate_message(self, session_id, question, turn_id, claim):
        turn = {}
        snapshot = watches.version_info(self.actions.data_version())

        def ask(history, retry=None):
            note = today_note(self.actions, session_id)
            if retry:
                note = SystemMessage(content=f'{note.content}\n{retry}', name='data_date')
            messages = history + [note, HumanMessage(content=question)]
            try:
                with selection_context(messages), plan_context(messages), action_context(self.actions, session_id, turn_id):
                    result = self.agent.invoke({'messages': messages}, {'recursion_limit': 16})
            except GraphRecursionError as exc:
                raise AgentIncompleteError('The assistant needed too many steps and stopped before answering.') from exc
            except openai.APIError as exc:
                raise ModelUnavailableError(_model_problem(exc)) from exc
            final = result['messages'][-1]
            if final.type != 'ai' or getattr(final, 'tool_calls', None):
                raise AgentIncompleteError('The assistant did not finish its answer.')
            content = final.content
            if isinstance(content, list):
                content = ''.join(block.get('text', '') for block in content if isinstance(block, dict))
            if not isinstance(content, str) or not content.strip():
                raise AgentIncompleteError('The assistant returned an empty answer.')
            return result['messages'], result['messages'][len(messages):], content

        def generate(saved):
            history = messages_from_dict(saved)
            everything, new, content = ask(history)
            # Figures stated with no lookup at all this turn: ask once more, telling the model to look them up.
            turn['retried'] = needs_lookup(content, new, question, history)
            if turn['retried']:
                everything, new, content = ask(history, retry=RETRY_NOTE)
            else:
                # An overdue figure attached to the wrong order: ask once more with the order named.
                wrong = misattributed(content, new, question, history)
                if wrong:
                    turn['retried'] = True
                    everything, new, content = ask(history, retry=ATTRIBUTION_NOTE.format(items='; '.join(wrong)))
            turn['messages'], turn['earlier'] = new, history
            turn['answer'] = content
            # Store the normalized answer and frozen evidence before committing the turn.
            everything[-1].content = content
            turn['evidence'], turn['check'] = _record_turn(everything[-1], new, question, history, turn['retried'])
            return messages_to_dict(_saved(everything)), content

        def commit_response(conn):
            self.actions.activate_turn(conn, turn_id)
            details = turn_details(turn.get('messages', []), include_evidence=False)
            # Read the newly activated cards through this same transaction, not a second
            # connection that would still see DRAFT until the transaction commits.
            proposals = []
            for proposal in details['proposals']:
                row = conn.execute('SELECT * FROM action_proposals WHERE id=?', (proposal['id'],)).fetchone()
                if row is not None:
                    proposals.append(self.actions._proposal(row))
            details['proposals'] = proposals
            details['evidence'] = turn['evidence']
            turn['response'] = {'session_id': session_id, 'answer': turn['answer'], **details,
                                'answer_check': turn['check'], 'prompt_version': PROMPT_VERSION}
            # The response, history and proposal activation either all commit or all roll back.
            self.store.complete_chat_request(conn, claim, turn['response'])

        with rules.data_context(snapshot['version'], snapshot['date']):
            self.store.update_turn(session_id, generate, on_commit=commit_response)
            return turn['response']

    def morning_briefing(self, session_id):
        """Generate an on-demand briefing locally and persist it in the conversation."""
        from briefing import get_morning_briefing, render_briefing_text

        def generate(saved):
            report = get_morning_briefing()
            if report['status'] != 'ok':
                raise RuntimeError('Briefing could not be generated.')
            answer = render_briefing_text(report)
            call_id = str(uuid4())
            new = [
                HumanMessage(content='Show the morning briefing for the dataset reference date.'),
                AIMessage(content='', tool_calls=[{'name': 'get_morning_briefing',
                    'args': {'as_of_date': rules.today_iso()}, 'id': call_id, 'type': 'tool_call'}]),
                ToolMessage(content=json.dumps(report), name='get_morning_briefing', tool_call_id=call_id),
                AIMessage(content=answer),
            ]
            _record_turn(new[-1], new[1:], new[0].content)
            messages = messages_from_dict(saved) + new
            return messages_to_dict(messages), answer

        snapshot = watches.version_info(self.actions.data_version())
        with rules.data_context(snapshot['version'], snapshot['date']):
            return {'session_id': session_id, 'answer': self.store.update_turn(session_id, generate)}
