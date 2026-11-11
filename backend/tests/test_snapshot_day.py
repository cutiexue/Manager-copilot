"""Loading a scripted snapshot moves the whole app to that day: chat tools, briefing, evidence and watches
all read the same orders, and the scripted values are named as simulated."""

import json

from langchain_core.messages import AIMessage

import evidence_refs
import rules
from actions import ActionStore
from briefing import get_briefing_payload
from data_loader import load_course_orders, load_orders
from llm import execute_tool
from storage import SQLiteStore
from tests.test_chat_actions import make
from tools import get_order_status, get_orders_at_risk, trace_order
from watches import order_state


def store_at(tmp_path, version):
    store = SQLiteStore(tmp_path / "app.db")
    store.setup()
    actions = ActionStore(store)
    actions.setup()
    if version != "v0":
        actions.set_data_version(version)
    return actions


def test_course_data_is_unchanged_on_v0(tmp_path):
    store_at(tmp_path, "v0")
    assert rules.today_iso() == "2026-04-01"
    assert load_orders() == load_course_orders()
    assert get_order_status("ORD-107")["data"]["current_stage"] == "PACKING"


def test_chat_tools_and_watches_agree_after_loading_v1(tmp_path):
    store_at(tmp_path, "v1")
    assert rules.today_iso() == "2026-04-02"
    order = get_order_status("ORD-107")["data"]
    assert (order["status"], order["completed_date"]) == ("COMPLETE", "2026-04-02")
    assert order == order_state("ORD-107", "v1")
    assert "ORD-107" not in {o["order_id"] for o in get_orders_at_risk()["data"]}
    assert trace_order("ORD-120")["snapshot_date"] == "2026-04-02"
    assert execute_tool("get_overdue_orders", "{}")["as_of_date"] == "2026-04-02"
    # The course date is now another day, so it needs an explicit scenario like any other date.
    assert execute_tool("get_overdue_orders", json.dumps({"as_of_date": "2026-04-01"}))["status"] == "error"


def test_evidence_shows_the_scripted_values_and_says_so(tmp_path):
    store_at(tmp_path, "v1")
    row = evidence_refs.lookup("orders.csv", 81)["data"]
    assert row["order_id"] == "ORD-107" and row["status"] == "COMPLETE"
    assert row["scripted_change"].endswith("from snapshot v1 (track1/scenarios/watch_snapshots.json)")
    untouched = evidence_refs.lookup("orders.csv", 2)["data"]
    assert "scripted_change" not in untouched


def test_briefing_follows_the_loaded_day(tmp_path):
    store_at(tmp_path, "v2")
    briefing = get_briefing_payload()["briefing"]
    assert briefing["as_of_date"] == briefing["snapshot_date"] == "2026-04-03"
    assert "ORD-114" not in {o["order_id"] for o in briefing["at_risk"]["orders"]}


def test_reset_returns_to_the_course_data(tmp_path):
    actions = store_at(tmp_path, "v2")
    actions.set_data_version("v0")
    assert rules.today_iso() == "2026-04-01" and load_orders() == load_course_orders()


def test_a_restart_keeps_the_loaded_day(tmp_path):
    store_at(tmp_path, "v1")
    rules.set_current_data("v0", rules.SNAPSHOT)  # as if the process restarted
    store_at(tmp_path, "v0")  # setup() reads the saved version back
    assert rules.today_iso() == "2026-04-02"


def test_the_model_is_told_the_day_but_the_note_is_not_saved(tmp_path):
    seen = []
    service, client = make(tmp_path, [AIMessage(content="Today is 2 April.")])
    original = service.agent.invoke

    def spy(state, config):
        seen.extend(m.content for m in state["messages"] if m.type == "system")
        return original(state, config)

    service.agent.invoke = spy
    service.actions.set_data_version("v1")
    session = client.post("/sessions", json={"title": "t"}).json()["id"]
    client.post(f"/sessions/{session}/messages", json={"message": "What day is it?"})
    assert any("2026-04-02" in text and "simulated" in text for text in seen)
    stored = service.store.get_history(session)
    assert not [m for m in stored if m.get("type") == "system"]
