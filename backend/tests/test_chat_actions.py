"""Chat turns return their tool calls, cited rows and proposals; only the API confirms a proposal."""

import pytest
from fastapi.testclient import TestClient
from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from api import create_app
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
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}])


def make(tmp_path, script):
    store = SQLiteStore(tmp_path / "app.db")
    store.setup()
    agent = create_agent(ScriptedModel(script=script), tools=build_tools(), system_prompt=SYSTEM_PROMPT)
    service = ChatService(store, agent=agent)
    return service, TestClient(create_app(service))


def test_a_chat_turn_proposes_but_only_the_confirm_button_saves(tmp_path):
    service, client = make(tmp_path, [
        call("trace_order", {"order_id": "ord-002"}, "c1"),
        call("propose_reminder", {"text": "Chase Cotton Club about ORD-002", "when": "tomorrow 09:00",
                                  "order_id": "ORD-002"}, "c2"),
        AIMessage(content="ORD-002 is 3 days late. I've prepared a reminder; confirm it in the app."),
    ])
    session_id = client.post("/sessions", json={}).json()["id"]
    reply = client.post(f"/sessions/{session_id}/messages", json={"message": "Remind me to chase ORD-002"}).json()

    assert [(c["name"], c["status"]) for c in reply["tool_calls"]] == [("trace_order", "ok"), ("propose_reminder", "proposed")]
    assert {"source": "track1/data/orders.csv", "row": 86, "key": "ORD-002"} in reply["evidence"]["refs"]
    assert reply["evidence"]["rows"]["track1/data/orders.csv#86"]["customer"] == "Cotton Club"
    [proposal] = reply["proposals"]
    assert (proposal["kind"], proposal["status"], proposal["session_id"]) == ("reminder", "PROPOSED", session_id)
    assert reply["prompt_version"]
    assert service.actions.list_reminders() == []  # the model's words do not save anything

    history = client.get(f"/sessions/{session_id}/messages").json()
    assert history[-1]["proposals"][0]["id"] == proposal["id"]
    assert history[-1]["evidence"]["refs"]

    first = client.post(f"/actions/{proposal['id']}/confirm").json()
    second = client.post(f"/actions/{proposal['id']}/confirm").json()
    assert (first["already_done"], second["already_done"]) == (False, True)
    assert len(client.get("/reminders").json()) == 1
    assert client.get(f"/sessions/{session_id}/messages").json()[-1]["proposals"][0]["status"] == "EXECUTED"
    audit = [(e["actor"], e["event"]) for e in reversed(client.get("/audit").json())]
    assert audit == [("agent", "proposal_created"), ("user", "confirmed"), ("system", "executed")]


def test_ui_proposals_follow_the_same_rules(tmp_path):
    _, client = make(tmp_path, [])
    note = client.post("/actions/proposals", json={"kind": "note", "payload": {"order_id": "ORD-107", "text": "Partial ok"}})
    assert note.status_code == 201
    note_id = note.json()["id"]
    assert client.post(f"/actions/{note_id}/cancel").json()["status"] == "CANCELLED"
    refused = client.post(f"/actions/{note_id}/confirm")
    assert (refused.status_code, refused.json()["code"]) == (409, "ACTION_STATE")
    bad = client.post("/actions/proposals", json={"kind": "note", "payload": {"order_id": "ORD-999", "text": "x"}})
    assert (bad.status_code, bad.json()["code"]) == (400, "INVALID_REQUEST")
    missing = client.post("/actions/nope/confirm")
    assert (missing.status_code, missing.json()["code"]) == (404, "NOT_FOUND")
    assert client.get("/notes").json() == []


def test_watches_alert_on_the_next_scripted_snapshot(tmp_path):
    _, client = make(tmp_path, [])
    proposal = client.post("/actions/proposals", json={"kind": "watch", "payload": {
        "order_id": "ORD-062", "condition": "not_moved_by", "deadline": "2026-04-02"}}).json()
    watch_id = client.post(f"/actions/{proposal['id']}/confirm").json()["result"]["id"]
    assert client.get("/data/snapshot").json()["current"]["version"] == "v0"

    advanced = client.post("/dev/data/advance").json()
    assert advanced["current"]["date"] == "2026-04-02"
    assert advanced["check"]["outcomes"][0]["result"] == "met"
    [alert] = client.get("/alerts", params={"unread": True}).json()
    assert alert["title"] == "Watch · ORD-062"
    assert client.get(f"/watches/{watch_id}").json()["status"] == "TRIGGERED"
    paused = client.post(f"/watches/{watch_id}/pause")
    assert (paused.status_code, paused.json()["code"]) == (409, "ACTION_STATE")
    assert client.get("/follow-ups/counts").json()["unread_alerts"] == 1
    client.post(f"/alerts/{alert['id']}/read")
    assert client.get("/follow-ups/counts").json()["unread_alerts"] == 0

    client.post("/dev/data/advance")
    last = client.post("/dev/data/advance")
    assert (last.status_code, last.json()["code"]) == (409, "ACTION_STATE")
    assert client.post("/dev/data/reset").json()["current"]["version"] == "v0"


def test_manual_briefing_runs_are_stored(tmp_path):
    _, client = make(tmp_path, [])
    created = client.post("/dev/briefings/generate")
    assert created.status_code == 201 and created.json()["created"]
    [run] = client.get("/briefings").json()
    assert (run["trigger"], run["as_of_date"]) == ("manual", "2026-04-01")
    assert client.get("/scheduler").json() == {"running": False, "jobs": []}
