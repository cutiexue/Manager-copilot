"""Standing watches on scripted data snapshots: quiet until the condition holds, then one alert."""

from datetime import datetime

import pytest

import watches
from actions import APP_TZ, ActionStateError, ActionStore
from storage import SQLiteStore

NOW = datetime(2026, 10, 24, 13, 30, tzinfo=APP_TZ)


@pytest.fixture
def actions(tmp_path):
    store = SQLiteStore(tmp_path / "app.db")
    store.setup()
    store_actions = ActionStore(store)
    store_actions.setup()
    return store_actions


def watch(actions, **payload):
    proposal = actions.propose("watch", payload, "chat", now=NOW)
    return actions.confirm(proposal["id"], now=NOW)["result"]


def test_snapshots_start_from_the_course_data_and_accumulate():
    assert [v["version"] for v in watches.load_snapshots()] == ["v0", "v1", "v2"]
    assert watches.order_state("ORD-107", "v0")["status"] == "IN_PROGRESS"
    assert watches.order_state("ORD-107", "v1")["status"] == "COMPLETE"
    assert watches.order_state("ORD-108", "v1")["current_stage"] == "WASHING"
    assert watches.order_state("ORD-108", "v2")["current_stage"] == "PACKING"
    assert watches.next_version("v2") is None


def test_each_condition_fires_once_on_the_snapshot_where_it_holds(actions):
    not_moved = watch(actions, order_id="ORD-062", condition="not_moved_by", deadline="2026-04-02")
    moved_in_time = watch(actions, order_id="ORD-120", condition="not_moved_by", deadline="2026-04-02")
    completed = watch(actions, order_id="ORD-107", condition="completed")
    overdue = watch(actions, order_id="ORD-029", condition="becomes_overdue")
    stage = watch(actions, order_id="ORD-108", condition="reaches_stage", stage="PACKING")

    first = {o["watch_id"]: o["result"] for o in watches.check_watches(actions, NOW)["outcomes"]}
    assert set(first.values()) == {"not_met"}

    actions.set_data_version("v1", now=NOW)
    second = {o["watch_id"]: o["result"] for o in watches.check_watches(actions, NOW)["outcomes"]}
    assert second == {not_moved["id"]: "met", moved_in_time["id"]: "resolved", completed["id"]: "met",
                      overdue["id"]: "met", stage["id"]: "not_met"}
    assert watches.check_watches(actions, NOW)["checked"] == 1  # only the stage watch is still active

    actions.set_data_version("v2", now=NOW)
    assert [o["result"] for o in watches.check_watches(actions, NOW)["outcomes"]] == ["met"]
    alerts = actions.list_alerts()
    assert len(alerts) == 4 and all(a["kind"] == "watch" for a in alerts)
    assert {w["status"] for w in actions.list_watches()} == {"TRIGGERED", "RESOLVED"}


def test_paused_and_cancelled_watches_stay_quiet(actions):
    paused = watch(actions, order_id="ORD-107", condition="completed")
    cancelled = watch(actions, order_id="ORD-062", condition="not_moved_by", deadline="2026-04-02")
    actions.set_watch_status(paused["id"], "pause", now=NOW)
    actions.set_watch_status(cancelled["id"], "cancel", now=NOW)
    with pytest.raises(ActionStateError):
        actions.set_watch_status(cancelled["id"], "resume", now=NOW)
    actions.set_data_version("v1", now=NOW)
    assert watches.check_watches(actions, NOW)["checked"] == 0
    assert actions.list_alerts() == []
    actions.set_watch_status(paused["id"], "resume", now=NOW)
    assert [o["result"] for o in watches.check_watches(actions, NOW)["outcomes"]] == ["met"]
    events = [e["event"] for e in actions.list_audit()]
    assert {"watch_paused", "watch_resumed", "watch_cancelled", "watch_triggered"} <= set(events)


def test_watches_that_could_never_fire_are_refused(actions):
    for payload, reason in [
        ({"order_id": "ORD-107", "condition": "becomes_overdue"}, "already overdue"),
        ({"order_id": "ORD-057", "condition": "completed"}, "already complete"),
        ({"order_id": "ORD-062", "condition": "not_moved_by"}, "needs a deadline"),
        ({"order_id": "ORD-062", "condition": "not_moved_by", "deadline": "2026-03-01"}, "before the current data date"),
        ({"order_id": "ORD-107", "condition": "reaches_stage", "stage": "KNITTING"}, "already at PACKING"),
        ({"order_id": "ORD-062", "condition": "teleports"}, "condition must be one of"),
    ]:
        with pytest.raises(ValueError, match=reason):
            actions.propose("watch", payload, "chat", now=NOW)
