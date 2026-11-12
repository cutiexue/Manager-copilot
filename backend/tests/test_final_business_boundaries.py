"""Missing records and scenario assumptions must not become asserted business facts."""

import json

import pytest
from langchain_core.messages import ToolMessage

import period_output
import rules
from evidence_refs import collect
from outsourcing_risk import workshop_profile
from data_loader import load_workshops
from plan_context import plan_context, revise_order_plan
from production_estimates import (
    WORKSHOP_ESTIMATORS, estimate_in_house, estimate_production_plan, estimate_quickstitch,
)
from production_optimizer import (
    optimize_cheapest_plan, optimize_fastest_plan, optimize_orders_cheapest,
    optimize_orders_outsourced,
)
from tool_schemas import TOOLS


def test_absent_week_is_unknown_not_a_total_collapse():
    result = period_output.compare_stage_periods(
        "2026-03-23", "2026-03-29", "2026-04-01", "2026-04-07")
    assert result["status"] == "insufficient_data"
    assert result["largest_decline"] is None and result["largest_increase"] is None
    assert result["complete_records"] is False
    for stage in result["stages"]:
        assert stage["first_total"] > 0
        assert stage["second_total"] is None and stage["second_recorded_total"] == 0
        assert stage["change"] is None and stage["change_percent"] is None
        assert stage["comparable"] is False


def test_partly_recorded_period_preserves_observations_without_claiming_a_full_total():
    result = period_output.summarize_stage_output("2026-03-30", "2026-04-02", "ASSEMBLY")
    [stage] = result["stages"]
    assert result["status"] == stage["status"] == "partial"
    assert stage["total_pieces"] is None and stage["recorded_total_pieces"] > 0
    assert stage["recorded_workdays"] == 2 and len(stage["source_rows"]) == 2
    comparison = period_output.compare_stage_periods(
        "2026-03-26", "2026-03-28", "2026-03-30", "2026-04-02", "ASSEMBLY")
    assert comparison["status"] == "partial"
    assert comparison["stages"][0]["change"] is None
    assert comparison["largest_decline"] is None and comparison["largest_increase"] is None


@pytest.mark.parametrize("output,decline,increase", [
    (0, "KNITTING", None), (50, "KNITTING", None),
    (100, None, None), (150, None, "KNITTING"),
])
def test_rankings_respect_direction_and_recorded_zero_is_real(monkeypatch, output, decline, increase):
    records = [
        {"date": "2026-03-02", "stage": "KNITTING", "pieces_completed": "100"},
        {"date": "2026-03-03", "stage": "KNITTING", "pieces_completed": str(output)},
    ]
    monkeypatch.setattr(period_output, "load_production", lambda: records)
    monkeypatch.setattr(period_output, "production_row_numbers", lambda: {
        (r["date"], r["stage"]): i + 2 for i, r in enumerate(records)})
    result = period_output.compare_stage_periods(
        "2026-03-02", "2026-03-02", "2026-03-03", "2026-03-03", "KNITTING")
    assert result["status"] == "ok" and result["complete_records"]
    assert result["stages"][0]["second_total"] == output
    assert result["stages"][0]["change_percent"] == output - 100
    assert result["largest_decline"] == decline and result["largest_increase"] == increase


def test_transport_profile_matches_the_once_per_batch_calculation():
    row = next(r for r in load_workshops() if r["workshop_id"] == "W5")
    profile = workshop_profile(row)
    assert any("fixed transport overhead per batch" in flag for flag in profile["flags"])
    assert all("each way" not in flag for flag in profile["flags"])


def test_global_largest_ranking_is_withheld_if_other_requested_stages_are_missing(monkeypatch):
    records = [{"date": day, "stage": "KNITTING", "pieces_completed": output}
               for day, output in [("2026-03-02", "100"), ("2026-03-03", "50")]]
    monkeypatch.setattr(period_output, "load_production", lambda: records)
    monkeypatch.setattr(period_output, "production_row_numbers", lambda: {
        (r["date"], r["stage"]): i + 2 for i, r in enumerate(records)})
    result = period_output.compare_stage_periods("2026-03-02", "2026-03-02", "2026-03-03", "2026-03-03")
    assert result["status"] == "partial"
    assert result["stages"][0]["change_percent"] == -50
    assert result["largest_decline"] is None and result["largest_increase"] is None


@pytest.mark.parametrize("make_plan", [
    lambda: estimate_in_house(100),
    lambda: estimate_quickstitch("TOPS", 100),
    lambda: estimate_production_plan("TOPS", 100, 0, [{"workshop_id": "W2", "pieces": 100}]),
    lambda: optimize_fastest_plan("TOPS", 100),
    lambda: optimize_cheapest_plan("TOPS", 100, 20),
    lambda: optimize_orders_outsourced("original_order_pieces", scope="all", order_ids=["ORD-001"]),
    lambda: optimize_orders_cheapest("original_order_pieces", 30, scope="all", order_ids=["ORD-001"]),
])
def test_new_scenarios_default_to_current_data_date_but_disclose_reference_age(make_plan):
    rules.set_current_data("v1", "2026-04-02")
    result = make_plan()
    assert result["status"] == "ok", result
    assert result["start_date"] == result["scenario_start_date"] == "2026-04-02"
    assert result["data_as_of"] == "2026-04-01"


def test_explicit_historical_start_is_preserved_for_a_saved_plan_revision():
    saved = optimize_orders_outsourced(
        "original_order_pieces", scope="all", order_ids=["ORD-001"], start_date="2026-04-01")
    assert saved["status"] == "ok"
    rules.set_current_data("v1", "2026-04-02")
    with plan_context([ToolMessage(content=json.dumps(saved), name="optimize_orders_outsourced", tool_call_id="p")]):
        revised = revise_order_plan(5, "completion_date")
    assert revised["status"] == "ok", revised
    assert revised["start_date"] == revised["scenario_start_date"] == "2026-04-01"
    assert revised["comparison"]["base_start_date"] == "2026-04-01"
    assert revised["order_selection_as_of"] == "2026-04-02"


def test_original_inhouse_workload_cites_original_snapshot_even_after_a_transition():
    rules.set_current_data("v1", "2026-04-02")
    result = estimate_in_house(100)
    assert result["open_order_load"]["data_version"] == "v0"
    refs = [r for r in collect(result, versioned=True) if r["source"].endswith("orders.csv")]
    assert len(refs) == 34
    assert {r["data_version"] for r in refs} == {"v0"}


def test_infeasible_scenario_still_exposes_its_dates():
    rules.set_current_data("v1", "2026-04-02")
    plans = [
        optimize_cheapest_plan("ACCESSORIES", 5000, 1),
        optimize_orders_cheapest("original_order_pieces", 1, scope="all", order_ids=["ORD-001"]),
    ]
    for plan in plans:
        assert plan["status"] == "infeasible"
        assert plan["scenario_start_date"] == plan["start_date"] == "2026-04-02"
        assert plan["data_as_of"] == "2026-04-01"


def test_all_feasibility_tool_schemas_document_current_date_default():
    names = {fn.__name__ for fn in WORKSHOP_ESTIMATORS.values()} | {
        "estimate_in_house", "estimate_production_plan", "optimize_fastest_plan",
        "optimize_cheapest_plan", "optimize_orders_outsourced", "optimize_orders_cheapest",
    }
    checked = set()
    for spec in TOOLS:
        function = spec["function"]
        if function["name"] in names:
            description = function["parameters"]["properties"]["start_date"]["description"]
            assert "current data date" in description and "reference data" in description
            checked.add(function["name"])
    assert checked == names
