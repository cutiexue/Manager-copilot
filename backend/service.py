"""Shared Python interface used by both the CLI and HTTP adapter."""

from langchain_core.messages import HumanMessage, messages_from_dict, messages_to_dict
from llm import build_agent


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
            result = self.agent.invoke({'messages': messages}, {'recursion_limit': 16})
            final = result['messages'][-1]
            if final.type != 'ai' or getattr(final, 'tool_calls', None):
                raise RuntimeError('Agent did not finish its answer.')
            content = final.content
            if isinstance(content, list):
                content = ''.join(block.get('text', '') for block in content if isinstance(block, dict))
            if not isinstance(content, str) or not content.strip():
                raise RuntimeError('Agent returned an empty answer.')
            return messages_to_dict(result['messages']), content

        answer = self.store.update_turn(session_id, generate)
        return {'session_id': session_id, 'answer': answer}
