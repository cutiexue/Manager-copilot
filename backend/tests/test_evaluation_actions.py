"""End-to-end versions of the action and watch questions Evaluation Report V1 left unverified (Q32-Q39).

Each test drives the same HTTP endpoints the web app uses, with real proposals and watches created
first (the fixtures the report said were missing), and checks the stored state, not only the reply.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from langchain_core.messages import AIMessage

from actions import APP_TZ, ActionStore
from scheduler import run_reminders
from storage import SQLiteStore
from tests.test_chat_actions import call, make


def propose(client, kind, payload):
    response = client.post("/actions/proposals", json={"kind": kind, "payload": payload})
    assert response.status_code == 201, response.json()
    return response.json()


def note(client, order_id, text="The customer has requested priority handling."):
    return propose(client, "note", {"order_id": order_id, "text": text})


def watch(client, order_id, deadline="2026-04-02"):
    proposal = propose(client, "watch", {"order_id": order_id, "condition": "not_moved_by", "deadline": deadline})
    return client.post(f"/actions/{proposal['id']}/confirm").json()["result"]["id"]


def test_q32_after_confirm_the_next_turn_knows_the_note_is_saved(tmp_path):
    seen = []
    service, client = make(tmp_path, [
        call("propose_order_note", {"order_id": "ORD-001", "text": "Priority handling."}, "c1"),
        AIMessage(content="Ready to confirm."), AIMessage(content="It is already saved.")])
    original = service.agent.invoke
    service.agent.invoke = lambda state, config: (seen.append(state["messages"][-2].content), original(state, config))[1]
    session = client.post("/sessions", json={"title": "t"}).json()["id"]
    [proposal] = client.post(f"/sessions/{session}/messages", json={"message": "Add a priority note to ORD-001"}).json()["proposals"]
    client.post(f"/actions/{proposal['id']}/confirm")
    client.post(f"/sessions/{session}/messages", json={"message": "Confirm the note proposal."})
    assert "proposals" not in seen[0]  # the first turn creates the proposal
    assert proposal["id"] in seen[1] and "confirmed and saved" in seen[1]


def test_q33_cancelling_a_pending_note_saves_nothing(tmp_path):
    _, client = make(tmp_path, [])
    proposal = note(client, "ORD-001")
    cancelled = client.post(f"/actions/{proposal['id']}/cancel").json()
    assert cancelled["status"] == "CANCELLED" and client.get("/notes").json() == []
    late = client.post(f"/actions/{proposal['id']}/confirm")
    assert (late.status_code, late.json()["code"]) == (409, "ACTION_STATE")


def test_q34_confirming_one_of_two_proposals_leaves_the_other_pending(tmp_path):
    _, client = make(tmp_path, [])
    first, second = note(client, "ORD-001"), note(client, "ORD-002")
    client.post(f"/actions/{first['id']}/confirm")
    assert [n["order_id"] for n in client.get("/notes").json()] == ["ORD-001"]
    assert [p["id"] for p in client.get("/actions", params={"status": "PROPOSED"}).json()] == [second["id"]]


def test_q35_confirming_twice_saves_one_note_even_at_the_same_moment(tmp_path):
    _, client = make(tmp_path, [])
    proposal = note(client, "ORD-001")
    one, two = (client.post(f"/actions/{proposal['id']}/confirm").json() for _ in range(2))
    assert (one["already_done"], two["already_done"]) == (False, True)
    assert one["result"]["id"] == two["result"]["id"] and len(client.get("/notes").json()) == 1
    # Two confirms racing on separate connections still execute once.
    store = SQLiteStore(tmp_path / "race.db")
    store.setup()
    actions = ActionStore(store)
    actions.setup()
    raced = actions.propose("note", {"order_id": "ORD-002", "text": "x"}, "ui")
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda _: actions.confirm(raced["id"]), range(4)))
    assert len({r["result"]["id"] for r in results}) == 1 and len(actions.list_notes()) == 1
    executed = [e for e in actions.list_audit() if e["event"] == "executed" and e["proposal_id"] == raced["id"]]
    assert len(executed) == 1


def test_q36_a_reminder_fires_once_at_its_real_time(tmp_path):
    store = SQLiteStore(tmp_path / "app.db")
    store.setup()
    actions = ActionStore(store)
    actions.setup()
    before = datetime(2026, 4, 1, 10, 0, tzinfo=APP_TZ)  # an isolated clock, as the report asked
    proposal = actions.propose("reminder", {"text": "Follow up on ORD-002", "order_id": "ORD-002",
                                            "when": "2026-04-02T15:00"}, "chat", now=before)
    actions.confirm(proposal["id"], now=before)
    assert run_reminders(actions, datetime(2026, 4, 2, 14, 59, tzinfo=APP_TZ))["fired"] == []
    assert len(run_reminders(actions, datetime(2026, 4, 2, 15, 0, tzinfo=APP_TZ))["fired"]) == 1
    assert run_reminders(actions, datetime(2026, 4, 2, 15, 5, tzinfo=APP_TZ))["fired"] == []
    assert [a["kind"] for a in actions.list_alerts()] == ["reminder"]


def test_q37_q38_a_quiet_order_alerts_and_a_moved_order_resolves(tmp_path):
    _, client = make(tmp_path, [])
    quiet, moved = watch(client, "ORD-002"), watch(client, "ORD-120")
    client.post("/dev/data/advance")  # 2026-04-02: ORD-120 moves to WASHING, ORD-002 does not move
    assert client.get(f"/watches/{quiet}").json()["status"] == "TRIGGERED"
    assert client.get(f"/watches/{moved}").json()["status"] == "RESOLVED"
    watch_alerts = [a for a in client.get("/alerts").json() if a["kind"] == "watch"]
    assert [a["title"] for a in watch_alerts] == ["Watch · ORD-002"]


def test_q39_cancelling_one_watch_leaves_the_other_running(tmp_path):
    _, client = make(tmp_path, [])
    kept, cancelled = watch(client, "ORD-002"), watch(client, "ORD-062")
    assert client.post(f"/watches/{cancelled}/cancel").json()["status"] == "CANCELLED"
    client.post("/dev/data/advance")
    assert client.get(f"/watches/{kept}").json()["status"] == "TRIGGERED"
    assert client.get(f"/watches/{cancelled}").json()["status"] == "CANCELLED"
    assert [a["title"] for a in client.get("/alerts").json() if a["kind"] == "watch"] == ["Watch · ORD-002"]
