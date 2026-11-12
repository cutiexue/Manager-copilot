"""Outsourcing risk: workshop profiles from workshops.csv and the plan's defect and deadline risk."""

import pytest

from outsourcing_risk import plan_risk, workshop_profile
from data_loader import load_workshops
from production_estimates import estimate_in_house, estimate_production_plan, estimate_quickstitch
from production_optimizer import optimize_cheapest_plan, optimize_fastest_plan, optimize_orders_outsourced

ROWS = {row["workshop_id"]: row for row in load_workshops()}


def test_profile_quotes_the_dispatcher_note_and_flags_from_the_data():
    w1, w5, w7, w8 = (workshop_profile(ROWS[w]) for w in ("W1", "W5", "W7", "W8"))
    assert w1["dispatcher_note"] == "fastest in the region; quality slips under pressure"
    assert any("high defect rate (12%" in f for f in w1["flags"])
    assert any("slow pickup" in f for f in w5["flags"])
    assert any(f.startswith("suspended") for f in w7["flags"])
    assert any("at most 300 pieces" in f for f in w8["flags"])
    assert workshop_profile(ROWS["W2"])["flags"] == []
    assert w1["source"] == {"source": "track1/data/workshops.csv", "row": 2, "key": "W1"}


def test_independent_batches_combine():
    risk = plan_risk([{"workshop_id": "W1", "pieces": 300, "completion_date": "2026-04-07"},
                      {"workshop_id": "W2", "pieces": 170, "completion_date": "2026-04-06"}])
    assert risk["chance_all_batches_clean"] == pytest.approx(0.88 * 0.97, abs=1e-4)
    assert risk["chance_some_batch_needs_rework"] == pytest.approx(1 - 0.88 * 0.97, abs=1e-4)
    assert risk["expected_pieces_in_reworked_batches"] == pytest.approx(0.12 * 300 + 0.03 * 170, abs=0.1)
    assert risk["risk_level"] == "medium" and "deadline_date" not in risk


def test_a_redo_that_still_fits_the_deadline_has_no_lateness_in_this_scenario():
    risk = optimize_cheapest_plan("TOPS", 800, 25)["risk"]
    [w3] = risk["workshops"]
    assert (w3["workshop_id"], w3["completion_date"], w3["rework_scenario_arrival"]) == ("W3", "2026-04-13", "2026-04-20")
    assert risk["chance_some_batch_needs_rework"] == 0.09
    assert risk["chance_some_pieces_late"] == 0 and risk["pieces_that_could_be_late"] == 0
    assert risk["risk_level"] == "low" and "still arrive by the 25 Apr deadline" in risk["summary"]


def test_a_tight_deadline_turns_the_defect_rate_into_delivery_risk():
    risk = optimize_cheapest_plan("TOPS", 800, 12)["risk"]
    late = [w["workshop_id"] for w in risk["workshops"] if w["late_if_reworked"]]
    assert late == ["W3"] and risk["pieces_that_could_be_late"] == 690
    assert risk["chance_some_pieces_late"] == pytest.approx(0.09)
    assert risk["risk_level"] == "medium"
    # Only W3's pieces are at stake; W8's 110 pieces are said to be unaffected.
    assert "the other 110 pieces are unaffected" in risk["summary"]


def test_a_plan_that_leans_on_sloppy_shops_under_a_tight_deadline_is_a_high_risk_strategy():
    risk = plan_risk([{"workshop_id": "W1", "pieces": 600, "completion_date": "2026-04-08"},
                      {"workshop_id": "W3", "pieces": 460, "completion_date": "2026-04-09"},
                      {"workshop_id": "W5", "pieces": 400, "completion_date": "2026-04-09"},
                      {"workshop_id": "W2", "pieces": 100, "completion_date": "2026-04-04"}], deadline="2026-04-10")
    assert risk["chance_some_pieces_late"] == pytest.approx(1 - 0.88 * 0.91 * 0.94, abs=1e-4)
    assert risk["risk_level"] == "high" and risk["strategy_rating"] == "High-risk strategy"
    assert risk["risk_drivers"] == ["W1", "W3", "W5"]
    assert risk["pieces_that_could_be_late"] == 1460  # W2's 100 pieces stay safe
    assert risk["summary"].startswith("High-risk strategy. ")


def test_low_and_medium_plans_are_rated_too():
    assert optimize_cheapest_plan("TOPS", 800, 25)["risk"]["strategy_rating"] == "Low-risk strategy"
    medium = optimize_cheapest_plan("TOPS", 800, 12)["risk"]
    assert medium["strategy_rating"] == "Medium-risk strategy" and "risk_drivers" not in medium


def test_every_outsourcing_result_carries_risk_and_states_the_rework_assumption():
    results = [optimize_fastest_plan("TOPS", 800), optimize_cheapest_plan("TOPS", 800, 25),
               optimize_orders_outsourced("original_order_pieces", scope="all", order_ids=["ORD-107", "ORD-120"]),
               estimate_production_plan("TOPS", 400, 0, [{"workshop_id": "W2", "pieces": 400}]),
               estimate_quickstitch("TOPS", 300)]
    for result in results:
        assert result["status"] == "ok", result
        assert result["risk"]["status"] == "ok"
        assert any("full-redo scenario" in a and "not a guaranteed latest arrival" in a
                   for a in result["risk"]["assumptions"])
        assert any("delays only that workshop" in a for a in result["risk"]["assumptions"])


def test_in_house_only_work_has_no_workshop_risk():
    assert estimate_in_house(100)["status"] == "ok"
    plan = estimate_production_plan("TOPS", 100, 100, [])
    assert plan["risk"]["status"] == "no_outsourcing"
