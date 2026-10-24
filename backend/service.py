"""Shared Python interface used by both the CLI and HTTP adapter."""

import json

import openai
from langchain_core.messages import AIMessage, HumanMessage, messages_from_dict, messages_to_dict
from langgraph.errors import GraphRecursionError

import evidence_refs
from action_tools import action_context
from actions import ActionNotFoundError, ActionStore
from llm import PROMPT_VERSION, build_agent
from order_selection import selection_context
from plan_context import plan_context

# Cap on raw CSV rows returned with one answer (a full order list cites all 120).
MAX_EVIDENCE_ROWS = 200


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


def turn_details(messages, actions=None):
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
            results.append(result)
    refs = evidence_refs.collect(results)
    proposals = []
    for result in results:
        if result.get('status') == 'proposed' and isinstance(result.get('proposal'), dict):
            try:
                proposals.append(actions.get(result['proposal']['id']) if actions else result['proposal'])
            except ActionNotFoundError:
                continue
    return {'tool_calls': calls,
            'evidence': {'refs': refs, 'rows': evidence_refs.raw_rows(refs[:MAX_EVIDENCE_ROWS])},
            'proposals': proposals}


class ChatService:
    def __init__(self, store, config=None, agent=None):
        self.store = store
        self.actions = ActionStore(store)
        self.actions.setup()
        self.agent = agent if agent is not None else build_agent(config)

    def create_session(self, title='New conversation'):
        return self.store.create_session(title)

    def list_sessions(self):
        return self.store.list_sessions()

    def get_history(self, session_id):
        """Questions and answers; each answer that used tools carries its evidence and proposals."""
        messages = messages_from_dict(self.store.get_history(session_id))
        history, turn = [], []
        for message in messages:
            if message.type == 'human':
                turn = []
                if message.content:
                    history.append({'role': 'human', 'content': message.content})
                continue
            turn.append(message)
            if message.type == 'ai' and message.content and not getattr(message, 'tool_calls', None):
                item = {'role': 'ai', 'content': message.content}
                details = turn_details(turn, self.actions)
                if details['tool_calls']:
                    item.update(details)
                history.append(item)
        return history

    def send_message(self, session_id, message):
        if not isinstance(message, str) or not message.strip() or len(message) > 20000:
            raise ValueError('Message must contain 1 to 20000 characters.')
        turn = {}

        def generate(saved):
            messages = messages_from_dict(saved) + [HumanMessage(content=message.strip())]
            try:
                with selection_context(messages), plan_context(messages), action_context(self.actions, session_id):
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
            turn['messages'] = result['messages'][len(messages):]
            return messages_to_dict(result['messages']), content

        answer = self.store.update_turn(session_id, generate)
        return {'session_id': session_id, 'answer': answer,
                **turn_details(turn.get('messages', []), self.actions), 'prompt_version': PROMPT_VERSION}

    def morning_briefing(self, session_id):
        """Generate an on-demand briefing locally and persist it in the conversation."""
        from briefing import get_morning_briefing, render_briefing_text

        def generate(saved):
            report = get_morning_briefing()
            if report['status'] != 'ok':
                raise RuntimeError('Briefing could not be generated.')
            answer = render_briefing_text(report)
            messages = messages_from_dict(saved) + [
                HumanMessage(content='Show the morning briefing for the dataset reference date.'),
                AIMessage(content=answer),
            ]
            return messages_to_dict(messages), answer

        return {'session_id': session_id, 'answer': self.store.update_turn(session_id, generate)}
