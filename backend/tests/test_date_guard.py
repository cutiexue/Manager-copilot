"""Business tools default to the dataset date and refuse another date unless it is an explicit scenario."""

import json

import pytest

from llm import execute_tool
from rules import SNAPSHOT
from tools import get_overdue_orders

DATED = ("get_overdue_orders", "get_orders_at_risk", "discover_issues", "get_morning_briefing")


@pytest.mark.parametrize("name", DATED)
def test_omitted_date_means_the_dataset_date(name):
    result = execute_tool(name, "{}")
    assert result["status"] == "ok" and result["as_of_date"] == SNAPSHOT


@pytest.mark.parametrize("name", DATED)
def test_a_real_world_date_is_refused(name):
    result = execute_tool(name, json.dumps({"as_of_date": "2026-11-11"}))
    assert result["status"] == "error" and SNAPSHOT in result["message"]


def test_an_explicit_scenario_still_runs():
    result = execute_tool("get_overdue_orders", json.dumps({"as_of_date": "2026-04-10", "scenario": True}))
    assert result["status"] == "ok" and result["as_of_date"] == "2026-04-10"
    assert result["warnings"]  # still labelled as a scenario, not a fact


def test_default_answer_is_unchanged():
    assert execute_tool("get_overdue_orders", "{}") == get_overdue_orders(SNAPSHOT)


def test_a_reminder_card_says_it_runs_on_real_time(tmp_path):
    from datetime import datetime

    from actions import APP_TZ, ActionStore
    from storage import SQLiteStore

    store = SQLiteStore(tmp_path / "app.db")
    store.setup()
    actions = ActionStore(store)
    actions.setup()
    now = datetime(2026, 11, 11, 12, 0, tzinfo=APP_TZ)
    proposal = actions.propose("reminder", {"text": "Chase ORD-107", "when": "tomorrow 09:00",
                                            "order_id": "ORD-107"}, "chat", "s1", now=now)
    assert proposal["summary"].startswith("Reminder · Thu 12 Nov 2026 09:00 (real time) · ORD-107")
