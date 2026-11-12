"""The Orders page list: filters, and totals counted by the backend."""

import csv

from data_loader import DATA_DIR
from order_search import list_orders
from tools import get_overdue_orders


def _course_rows():
    with open(DATA_DIR / "orders.csv", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_all_orders_and_totals_match_the_csv():
    rows = _course_rows()
    result = list_orders()
    assert result["status"] == "ok"
    assert result["summary"]["orders"] == len(rows) == len(result["orders"])
    assert result["summary"]["pieces"] == sum(int(r["pieces"]) for r in rows)
    assert result["summary"]["unfinished"] == sum(r["status"] == "IN_PROGRESS" for r in rows)
    assert sum(s["orders"] for s in result["summary"]["by_stage"]) == len(rows)


def test_stage_chart_counts_at_risk_orders_per_stage():
    result = list_orders()
    by_stage = {s["stage"]: s for s in result["summary"]["by_stage"]}
    assert sum(s["at_risk"] for s in by_stage.values()) == result["summary"]["at_risk"] == 12
    assert by_stage["COMPLETE"]["at_risk"] == 0
    for stage, counts in by_stage.items():
        assert counts["at_risk"] == sum(1 for o in result["orders"]
                                        if o["current_stage"] == stage and o["risk_reasons"])
        assert counts["at_risk"] <= counts["orders"]


def test_overdue_filter_matches_the_overdue_tool():
    result = list_orders(due="overdue")
    overdue = get_overdue_orders()
    assert result["summary"]["orders"] == overdue["count"]
    assert result["summary"]["pieces"] == overdue["original_order_pieces"]
    assert {o["order_id"] for o in result["orders"]} == {o["order_id"] for o in overdue["data"]}


def test_filters_combine():
    unfinished = list_orders(status="unfinished")
    assert all(o["status"] == "IN_PROGRESS" for o in unfinished["orders"])
    washing = list_orders(status="unfinished", stage="WASHING")
    assert washing["orders"] and all(o["current_stage"] == "WASHING" for o in washing["orders"])
    customer = unfinished["orders"][0]["customer"]
    one = list_orders(customer=customer)
    assert one["orders"] and all(o["customer"] == customer for o in one["orders"])
    risky = list_orders(status="at_risk")
    assert risky["summary"]["at_risk"] == risky["summary"]["orders"] > 0


def test_due_window_counts_today_to_today_plus_n():
    result = list_orders(due="7d")
    for o in result["orders"]:
        assert "2026-04-01" <= o["due_date"] <= "2026-04-08"


def test_bad_filters_are_rejected():
    assert list_orders(status="late")["status"] == "error"
    assert list_orders(due="week")["status"] == "error"
