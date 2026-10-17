"""HTTP chat flow with a fake agent: no API key or network needed."""

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from api import create_app
from service import ChatService
from storage import SQLiteStore


class FakeAgent:
    """Stands in for the LangChain agent and echoes the last question."""

    def invoke(self, state, config):
        question = state["messages"][-1].content
        return {"messages": state["messages"] + [AIMessage(content=f"echo: {question}")]}


@pytest.fixture
def client(tmp_path):
    store = SQLiteStore(tmp_path / "app.db")
    store.setup()
    return TestClient(create_app(ChatService(store, agent=FakeAgent())))


def test_multi_turn_chat_is_persisted(client):
    session = client.post("/sessions", json={"title": "Demo"}).json()
    first = client.post(f"/sessions/{session['id']}/messages", json={"message": "Which orders are late?"})
    assert first.status_code == 200
    assert first.json()["answer"] == "echo: Which orders are late?"
    client.post(f"/sessions/{session['id']}/messages", json={"message": "Why?"})

    history = client.get(f"/sessions/{session['id']}/messages").json()
    assert [m["role"] for m in history] == ["human", "ai", "human", "ai"]
    assert [s["id"] for s in client.get("/sessions").json()] == [session["id"]]


def test_errors_map_to_http_status(client):
    assert client.get("/sessions/missing/messages").status_code == 404
    assert client.post("/sessions", json={"title": "x", "admin": True}).status_code == 400
    session_id = client.post("/sessions", json={}).json()["id"]
    assert client.post(f"/sessions/{session_id}/messages", json={"message": "  "}).status_code == 400
