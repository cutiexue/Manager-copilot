"""A concurrent data-day change must not mix facts with another snapshot's evidence.

These use the real deterministic tools, HTTP routes and temporary SQLite state. No
model is created or called; events make the otherwise intermittent race repeatable.
"""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

import briefing
import rules
import scheduler
import views
from actions import APP_TZ
from api import create_app
from service import ChatService
from storage import SQLiteStore

ORDER_ROW = "track1/data/orders.csv#81"


class NoAgent:
    def invoke(self, *args, **kwargs):
        raise AssertionError("Snapshot read views must not call the model")


@pytest.fixture
def service(tmp_path):
    store = SQLiteStore(tmp_path / "snapshot-race.db")
    store.setup()
    return ChatService(store, agent=NoAgent())


def assert_course_briefing(payload):
    report = payload["briefing"]
    assert report["as_of_date"] == report["snapshot_date"] == "2026-04-01"
    assert any(row["order_id"] == "ORD-107" for row in report["at_risk"]["orders"])
    assert payload["source_rows"][ORDER_ROW]["status"] == "IN_PROGRESS"


def test_concurrent_http_advance_cannot_change_in_flight_briefing_evidence(service, monkeypatch):
    original = briefing.get_morning_briefing
    computed, resume = threading.Event(), threading.Event()
    guard = threading.Lock()
    first = True

    def pause_after_first_calculation(*args, **kwargs):
        nonlocal first
        result = original(*args, **kwargs)
        with guard:
            pause, first = first, False
        if pause:
            computed.set()
            assert resume.wait(10), "Concurrent snapshot update did not release the request"
        return result

    monkeypatch.setattr(briefing, "get_morning_briefing", pause_after_first_calculation)
    with TestClient(create_app(service)) as client, ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(client.get, "/briefings/latest")
        try:
            assert computed.wait(10), "Briefing did not reach the evidence boundary"
            advanced = client.post("/dev/data/advance")
            assert advanced.status_code == 200
            assert advanced.json()["current"]["version"] == "v1"
        finally:
            resume.set()
        response = pending.result(timeout=10)
        assert response.status_code == 200
        assert_course_briefing(response.json())

        # The pin belongs to this request only: the next request sees the new data day.
        latest = client.get("/briefings/latest").json()["briefing"]
        assert latest["as_of_date"] == latest["snapshot_date"] == "2026-04-02"
        assert not any(row["order_id"] == "ORD-107" for row in latest["at_risk"]["orders"])


def test_direct_briefing_keeps_all_calculations_on_one_snapshot(service, monkeypatch):
    expected = briefing.get_morning_briefing()
    original = briefing.get_orders_at_risk

    def change_day_after_risk(*args, **kwargs):
        result = original(*args, **kwargs)
        service.actions.set_data_version("v1")
        return result

    monkeypatch.setattr(briefing, "get_orders_at_risk", change_day_after_risk)
    assert briefing.get_morning_briefing() == expected
    assert rules.current_version() == "v1"
    # Calling it as a chat tool must preserve the enclosing turn's older snapshot too.
    with rules.data_context("v0", "2026-04-01"):
        assert briefing.get_morning_briefing() == expected
    assert rules.current_version() == "v1"


def test_order_view_keeps_trace_and_raw_rows_together(service, monkeypatch):
    expected = views.order_detail("ORD-107", service.actions)
    original = views.trace_order

    def change_day_after_trace(*args, **kwargs):
        result = original(*args, **kwargs)
        service.actions.set_data_version("v1")
        return result

    monkeypatch.setattr(views, "trace_order", change_day_after_trace)
    result = views.order_detail("ORD-107", service.actions)
    assert result == expected
    assert result["evidence"]["rows"][ORDER_ROW]["status"] == "IN_PROGRESS"
    assert rules.current_version() == "v1"
    assert views.order_detail("ORD-107", service.actions)["trace"]["data"]["status"] == "COMPLETE"


def test_estimate_keeps_request_date_if_snapshot_advances_before_tool_execution(service, monkeypatch):
    expected = views.estimate("estimate_in_house", {"pieces": 500})
    original = views.execute_tool

    def change_day_then_execute(*args, **kwargs):
        service.actions.set_data_version("v1")
        return original(*args, **kwargs)

    monkeypatch.setattr(views, "execute_tool", change_day_then_execute)
    assert views.estimate("estimate_in_house", {"pieces": 500}) == expected
    assert rules.current_version() == "v1"
    assert views.estimate("estimate_in_house", {"pieces": 500})["result"]["scenario_start_date"] == "2026-04-02"


def test_scheduler_stores_one_consistent_payload_when_snapshot_changes(service, monkeypatch):
    original = scheduler.get_briefing_payload
    calls = []

    def change_day_then_build():
        service.actions.set_data_version("v1")
        calls.append(True)
        return original()

    monkeypatch.setattr(scheduler, "get_briefing_payload", change_day_then_build)
    result = scheduler.run_morning_briefing(
        service.actions, datetime(2026, 11, 12, 7, tzinfo=APP_TZ))
    assert result["created"] and len(calls) == 1
    with service.store.connection() as conn:
        row = conn.execute("SELECT payload FROM briefing_runs WHERE id=?", (result["run"]["id"],)).fetchone()
    assert_course_briefing(json.loads(row["payload"]))
    assert rules.current_version() == "v1"
    assert "2026-04-01" in service.actions.list_alerts()[0]["body"]
