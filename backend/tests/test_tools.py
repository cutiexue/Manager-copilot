"""Tool outputs pinned to figures independently recomputed from the raw CSVs."""

import pytest

from tools import (compare_stage_output, get_customer_orders, get_order_status,
                   get_orders_at_risk, get_stage_output, trace_order)

AT_RISK_IDS = ["ORD-120", "ORD-107", "ORD-114", "ORD-002", "ORD-083", "ORD-020",
               "ORD-103", "ORD-029", "ORD-093", "ORD-055", "ORD-108", "ORD-005"]


def test_orders_at_risk_on_snapshot_date():
    result = get_orders_at_risk("2026-04-01")
    assert result["count"] == 12
    assert [order["order_id"] for order in result["data"]] == AT_RISK_IDS
    assert len(result["source_rows"]) == 12


def test_trace_order_002():
    result = trace_order("ORD-002")
    assert result["status"] == "ok"
    assert result["data"]["customer"] == "Cotton Club"
    assert result["facts"]["overdue_calendar_days"] == 3
    assert result["facts"]["days_since_last_activity"] == 9
    assert result["evidence"]["order"] == [
        {"source": "track1/data/orders.csv", "row": 86, "key": "ORD-002"}]


@pytest.mark.parametrize("stage, pieces, baseline, change", [
    ("KNITTING", 905, 939.0, -3.62),
    ("ASSEMBLY", 455, 515.71, -11.77),
    ("WASHING", 732, 731.71, 0.04),
    ("PACKING", 657, 658.29, -0.2),
])
def test_yesterday_vs_previous_seven_workdays(stage, pieces, baseline, change):
    result = compare_stage_output(stage, "2026-03-31")
    assert result["status"] == "ok"
    assert result["data"]["pieces_completed"] == pieces
    assert result["data"]["baseline_average"] == baseline
    assert result["data"]["change_percent"] == change
    assert len(result["baseline_records"]) == 7


def test_sunday_is_not_compared():
    assert compare_stage_output("ASSEMBLY", "2026-03-29")["status"] == "not_applicable"


def test_too_little_history_is_reported_not_guessed():
    assert compare_stage_output("KNITTING", "2026-01-03")["status"] == "insufficient_data"


def test_missing_records_are_not_zero():
    result = get_stage_output("KNITTING", "2026-04-01")
    assert result["status"] == "not_found"
    assert "not zero" in result["message"]


def test_unknown_order_is_not_found():
    assert get_order_status("ORD-999") == {"status": "not_found", "data": None}


def test_customer_lookup_ignores_case_and_spaces():
    assert get_customer_orders(" trendcart ")["count"] == 17


@pytest.mark.xfail(strict=True, reason="Known gap: order IDs match case-sensitively (README).")
def test_order_id_lookup_ignores_case():
    assert get_order_status("ord-002")["status"] == "ok"
