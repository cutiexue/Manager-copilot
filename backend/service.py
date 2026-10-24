"""Shared Python interface used by both the CLI and HTTP adapter."""

import openai
from langchain_core.messages import AIMessage, HumanMessage, messages_from_dict, messages_to_dict
from langgraph.errors import GraphRecursionError
from llm import build_agent
from order_selection import selection_context
from plan_context import plan_context


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


class ChatService:
    def __init__(self, store, config=None, agent=None):
        self.store = store
        self.agent = agent if agent is not None else build_agent(config)

    def create_session(self, title='New conversation'):
        return self.store.create_session(title)

    def list_sessions(self):
        return self.store.list_sessions()

    def get_history(self, session_id):
        messages = messages_from_dict(self.store.get_history(session_id))
        return [{'role': message.type, 'content': message.content} for message in messages
                if message.type in ('human', 'ai') and message.content]

    def send_message(self, session_id, message):
        if not isinstance(message, str) or not message.strip() or len(message) > 20000:
            raise ValueError('Message must contain 1 to 20000 characters.')

        def generate(saved):
            messages = messages_from_dict(saved) + [HumanMessage(content=message.strip())]
            try:
                with selection_context(messages), plan_context(messages):
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
            return messages_to_dict(result['messages']), content

        answer = self.store.update_turn(session_id, generate)
        return {'session_id': session_id, 'answer': answer}

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
