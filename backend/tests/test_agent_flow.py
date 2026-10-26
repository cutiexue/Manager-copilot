"""Real create_agent loop and ChatService with a scripted model: no API key or network."""

import json

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from llm import SYSTEM_PROMPT, build_tools
from service import ChatService
from storage import SQLiteStore


class ScriptedModel(BaseChatModel):
    """Replays prepared AI messages in order, including tool calls."""

    script: list

    @property
    def _llm_type(self):
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return ChatResult(generations=[ChatGeneration(message=self.script.pop(0))])


def call(name, args, call_id):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id,
                                               "type": "tool_call"}])


def tool_results(store, session_id, name):
    return [json.loads(m["data"]["content"]) for m in store.get_history(session_id)
            if m["type"] == "tool" and m["data"]["name"] == name]


def test_follow_up_uses_the_saved_selection(tmp_path):
    # 第二轮在新的请求里只说“这些订单中的 TOPS”，必须从数据库里已保存的工具结果恢复选择。
    model = ScriptedModel(script=[
        call("query_orders", {"status": "IN_PROGRESS"}, "c1"), AIMessage(content="34 unfinished."),
        call("query_orders", {"scope": "selected", "category": "TOPS"}, "c2"), AIMessage(content="22 tops."),
    ])
    store = SQLiteStore(tmp_path / "app.db")
    store.setup()
    service = ChatService(store, agent=create_agent(model, tools=build_tools(), system_prompt=SYSTEM_PROMPT))
    session_id = service.create_session()["id"]

    assert service.send_message(session_id, "How many unfinished orders?")["answer"] == "34 unfinished."
    assert service.send_message(session_id, "How many of these are tops?")["answer"] == "22 tops."
    first, second = tool_results(store, session_id, "query_orders")
    assert first["count"] == 34
    assert (second["count"], second["original_order_pieces"]) == (22, 20450)
    assert store.list_sessions()[0]["title"] == "How many unfinished orders?"


def test_on_demand_briefing_is_saved_in_the_conversation(tmp_path):
    store = SQLiteStore(tmp_path / "app.db")
    store.setup()
    service = ChatService(store, agent=object())
    session_id = service.create_session()["id"]

    answer = service.morning_briefing(session_id)["answer"]
    assert "Orders at risk: 12" in answer
    assert [m["role"] for m in service.get_history(session_id)] == ["human", "ai"]
