"""Feasibility tools: eligibility on every call, honest limits and clear errors (review H-12, H-15)."""

import csv
import json
from datetime import date

from data_loader import DATA_DIR
from llm import execute_tool
from order_selection import selection_context
from plan_context import plan_context
from production_estimates import estimate_in_house, estimate_production_plan, estimate_quickstitch
from rules import MAX_BASELINE_WORKDAYS, SNAPSHOT


def run(name, args):
    return execute_tool(name, json.dumps(args))


def test_eligibility_is_checked_even_for_zero_pieces():
    assert run("estimate_oldmill", {"category": "TOPS", "pieces": 0})["message"] == (
        "W7 is not ACTIVE and cannot accept new work.")
    assert run("estimate_little_loom", {"category": "TOPS", "pieces": 0})["message"] == "W4 cannot make TOPS."
    assert run("estimate_steadyhands", {"category": "TOPS", "pieces": 0})["status"] == "ok"


def test_unused_allocation_rows_do_not_block_a_plan():
    plan = estimate_production_plan("TOPS", 300, 0, [{"workshop_id": "W1", "pieces": 300},
                                                     {"workshop_id": "W7", "pieces": 0}])
    assert plan["status"] == "ok"
    assert [b["producer"] for b in plan["branches"]] == ["W1"]


def test_quantities_and_queues_have_limits_instead_of_crashing():
    assert estimate_quickstitch("TOPS", 10**12)["message"] == "pieces must be an integer from 0 to 1000000."
    assert estimate_in_house(10**9)["status"] == "error"
    assert estimate_in_house(400, queue_workdays=1e12)["message"] == "queue_workdays must be a number from 0 to 365."
    assert run("estimate_quickstitch", {"category": "TOPS", "pieces": 10**12})["status"] == "error"


def test_baseline_limit_matches_the_workdays_in_the_production_log():
    with open(DATA_DIR / "production_log.csv", newline="") as handle:
        days = {row["date"] for row in csv.DictReader(handle)}
    workdays = [d for d in days if date.fromisoformat(d).weekday() != 6 and d < SNAPSHOT]
    assert MAX_BASELINE_WORKDAYS == len(workdays) == 77
    assert run("estimate_in_house", {"pieces": 400, "baseline_days": 77})["status"] == "ok"
    assert run("estimate_in_house", {"pieces": 400, "baseline_days": 78})["status"] == "error"


def test_missing_in_house_history_keeps_its_status():
    result = run("optimize_fastest_plan", {"category": "TOPS", "total_pieces": 800, "start_date": "2025-12-01"})
    assert result["status"] == "insufficient_data"
    assert "include_in_house to false" in result["message"]


def test_oversized_revision_is_explained_in_extra_days():
    with selection_context([]), plan_context([]):
        first = run("optimize_orders_outsourced", {
            "quantity_basis": "original_order_pieces", "scope": "all",
            "order_ids": ["ORD-002", "ORD-120", "ORD-093"], "expected_order_count": 3})
        assert first["status"] == "ok"
        too_far = run("revise_order_plan", {"extra_days": 3650, "deadline_basis": "completion_date"})
        assert too_far["status"] == "error"
        assert too_far["message"].startswith("extra_days is too large")
        assert "deadline_days" not in too_far["message"]
        assert run("revise_order_plan", {"extra_days": 5, "deadline_basis": "completion_date"})["status"] == "ok"
