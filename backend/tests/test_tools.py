"""Tool outputs pinned to figures independently recomputed from the raw CSVs."""

import pytest

from tools import (compare_stage_output, get_customer_orders, get_order_status,
                   get_orders_at_risk, get_overdue_orders, get_stage_output, trace_order)

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


def test_unknown_order_is_not_found_and_nothing_is_guessed():
    result = get_order_status("ORD-999")
    assert (result["status"], result["data"]) == ("not_found", None)
    assert "ORD-999" in result["message"]


def test_customer_lookup_ignores_case_and_spaces():
    assert get_customer_orders(" trendcart ")["count"] == 17


@pytest.mark.parametrize("spelling", ["ORD-002", "ord-002", "ORD002", " ord 2 ", "2"])
def test_order_id_lookup_accepts_any_spelling(spelling):
    assert get_order_status(spelling)["data"]["order_id"] == "ORD-002"


def test_a_unique_part_of_a_customer_name_is_resolved_and_said_so():
    result = get_customer_orders("maple")
    assert (result["customer"], result["count"]) == ("Maple & Co", 19)
    assert "Maple & Co" in result["note"]


def test_an_ambiguous_or_unknown_customer_returns_candidates_instead_of_a_guess():
    ambiguous = get_customer_orders("co")
    assert ambiguous["status"] == "ambiguous"
    assert set(ambiguous["candidates"]) == {"Cotton Club", "Maple & Co"}
    misspelt = get_customer_orders("Trend Kart")
    assert (misspelt["status"], misspelt["candidates"]) == ("not_found", ["TrendCart"])
    from tools import query_orders
    assert query_orders(customer="co")["status"] == "ambiguous"
    assert query_orders(customer="maple", status="IN_PROGRESS")["order_ids"] == ["ORD-083", "ORD-093"]
    assert query_orders(order_ids=["ord-83", "93"])["count"] == 2


def test_risk_result_states_its_thresholds_as_numbers():
    rules = get_orders_at_risk("2026-04-01")["rules"]
    assert (rules["quiet_order_days"], rules["due_within_days"]) == (7, 3)


def test_snapshot_date_spelled_differently_is_not_a_scenario():
    assert get_overdue_orders("20260401")["warnings"] == []
    assert get_orders_at_risk("20260401")["warnings"] == []
    assert get_overdue_orders("2026-03-30")["warnings"]
