"""HTTP chat flow with a fake agent and the briefing endpoint: no API key or network needed."""

import json
from pathlib import Path

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
    rest_day = client.get("/briefings/latest", params={"as_of_date": "2026-03-30"}).json()
    assert rest_day["briefing"]["yesterday"]["is_workday"] is False
    assert client.get("/briefings/latest", params={"as_of_date": "2026-13-01"}).status_code == 400
