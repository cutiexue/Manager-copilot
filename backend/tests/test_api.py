"""HTTP chat flow with a fake agent and the briefing endpoint: no API key or network needed."""

import json
from pathlib import Path

import httpx
import openai
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langgraph.errors import GraphRecursionError

import api
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


def error(response):
    """Every error has the same shape: a readable detail and a stable code."""
    body = response.json()
    assert set(body) == {"detail", "code"} and isinstance(body["detail"], str)
    return response.status_code, body["code"]


def test_errors_map_to_http_status(client):
    assert error(client.get("/sessions/missing/messages")) == (404, "SESSION_NOT_FOUND")
    assert error(client.post("/sessions", json={"title": "x", "admin": True})) == (400, "INVALID_REQUEST")
    session_id = client.post("/sessions", json={}).json()["id"]
    assert error(client.post(f"/sessions/{session_id}/messages", json={"message": "  "})) == (400, "INVALID_REQUEST")
    assert error(client.get("/no-such-route")) == (404, "NOT_FOUND")


def make_client(tmp_path, agent):
    store = SQLiteStore(tmp_path / "errors.db")
    store.setup()
    return TestClient(create_app(ChatService(store, agent=agent))), store


def test_a_bug_is_an_internal_error_not_a_missing_session(tmp_path, monkeypatch, caplog):
    def broken(as_of_date):
        return {}["missing"]

    monkeypatch.setattr(api, "get_briefing_payload", broken)
    client, _ = make_client(tmp_path, FakeAgent())
    with caplog.at_level("ERROR", logger="manager_copilot.api"):
        assert error(client.get("/briefings/latest")) == (500, "INTERNAL_ERROR")
    assert "Unexpected error" in caplog.text


class StuckAgent:
    def invoke(self, state, config):
        raise GraphRecursionError("Recursion limit of 16 reached")


class OfflineModelAgent:
    def invoke(self, state, config):
        raise openai.APIConnectionError(request=httpx.Request("POST", "https://api.example.test/v1/chat"))


def test_agent_and_model_failures_say_what_happened(tmp_path):
    client, _ = make_client(tmp_path, StuckAgent())
    session_id = client.post("/sessions", json={}).json()["id"]
    response = client.post(f"/sessions/{session_id}/messages", json={"message": "hi"})
    assert error(response) == (502, "AGENT_INCOMPLETE")
    assert "too many steps" in response.json()["detail"]

    client, _ = make_client(tmp_path, OfflineModelAgent())
    session_id = client.post("/sessions", json={}).json()["id"]
    response = client.post(f"/sessions/{session_id}/messages", json={"message": "hi"})
    assert error(response) == (503, "MODEL_UNAVAILABLE")
    assert response.json()["detail"] == "Cannot reach the model API. Check the network connection."
    # A failed turn saves nothing.
    assert client.get(f"/sessions/{session_id}/messages").json() == []


def test_a_conversation_changed_mid_turn_is_a_conflict(tmp_path):
    state = {}

    class InterruptedAgent:
        def invoke(self, agent_state, config):
            # Another request finishes a turn on the same conversation while this one is thinking.
            state["store"].update_turn(state["session"], lambda saved: (saved, "other turn"))
            return {"messages": agent_state["messages"] + [AIMessage(content="late answer")]}

    client, store = make_client(tmp_path, InterruptedAgent())
    state["store"] = store
    state["session"] = client.post("/sessions", json={}).json()["id"]
    assert error(client.post(f"/sessions/{state['session']}/messages", json={"message": "hi"})) == (409, "CONFLICT")


FIXTURE = Path(__file__).resolve().parents[2] / "frontend" / "src" / "fixtures" / "briefing.json"


def test_latest_briefing_matches_the_frontend_snapshot(client):
    # 前端在后端离线时退回快照，所以实时接口和快照必须是同一种结构、同样的内容。
    response = client.get("/briefings/latest")
    assert response.status_code == 200
    payload = response.json()
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert set(payload) == set(fixture)
    assert payload["generator"] == "GET /briefings/latest"
    assert payload["briefing"] == fixture["briefing"]
    assert payload["source_rows"] == fixture["source_rows"]
    assert payload["briefing_text"] == fixture["briefing_text"]
    assert payload["source_rows"]["track1/data/orders.csv#86"]["order_id"] == "ORD-002"


def test_latest_briefing_for_another_date_and_bad_date(client):
    monday = client.get("/briefings/latest", params={"as_of_date": "2026-03-30"}).json()
    assert (monday["briefing"]["yesterday"]["date"], monday["briefing"]["yesterday"]["label"]) == (
        "2026-03-28", "Last workday")
    assert error(client.get("/briefings/latest", params={"as_of_date": "2026-13-01"})) == (400, "INVALID_REQUEST")


def test_order_search_endpoint(client):
    result = client.get("/orders/search", params={"q": "maple", "limit": 5}).json()
    assert (result["total"], result["count"]) == (19, 5)
    assert error(client.get("/orders/search", params={"limit": 0})) == (400, "INVALID_REQUEST")
    # FastAPI's own type errors use the same shape, with a readable sentence instead of a list.
    response = client.get("/orders/search", params={"limit": "many"})
    assert error(response) == (400, "INVALID_REQUEST")
    assert response.json()["detail"].startswith("limit:")
