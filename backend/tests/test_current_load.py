"""C-1 and C-2: in-house estimates queue behind the unfinished orders, and "cheapest" does not
treat in-house production as free just because its cost is missing from the data."""

import csv
from pathlib import Path

import pytest

from production_estimates import estimate_in_house, estimate_production_plan, open_order_load
from production_optimizer import optimize_cheapest_plan, optimize_fastest_plan
from tool_schemas import TOOLS

DATA = Path(__file__).resolve().parents[1] / "track1" / "data"
STAGES = ("KNITTING", "ASSEMBLY", "WASHING", "PACKING")


def csv_rows(name):
    with (DATA / name).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_open_order_load_counts_each_order_from_its_current_stage():
    open_orders = [o for o in csv_rows("orders.csv") if o["status"] == "IN_PROGRESS"]
    expected = {stage: sum(int(o["pieces"]) for o in open_orders if STAGES.index(o["current_stage"]) <= i)
                for i, stage in enumerate(STAGES)}
    orders, by_stage, refs = open_order_load()
    assert len(orders) == len(refs) == 34
    assert by_stage == expected == {"KNITTING": 9900, "ASSEMBLY": 20500, "WASHING": 28850, "PACKING": 32850}


def test_new_batch_waits_for_the_load_ahead_at_every_stage():
    result = estimate_in_house(800)
    assert result["queue_basis"] == "open_orders"
    assert [s["open_order_workdays"] for s in result["stages"]] == [11, 44, 40, 51]
    # Knitting clears in 11 workdays, assembly in 44: the batch leaves each stage at these points.
    assert [s["finished_after_workdays"] for s in result["stages"]] == [12, 46, 48, 53]
    assert result["workdays_including_queue"] == 53 and result["completion_date"] == "2026-06-01"
    load = result["open_order_load"]
    assert (load["orders"], load["original_pieces"], load["upper_bound"]) == (34, 32850, True)
    assert any("upper bound" in a for a in result["assumptions"])


def test_queue_options_and_start_dates():
    # A flat queue given by the manager replaces the order load (0 = the old "line is free" answer).
    free = estimate_in_house(800, queue_workdays=0)
    assert (free["queue_basis"], free["completion_date"]) == ("given", "2026-04-08")
    assert estimate_in_house(800, queue_workdays=5)["workdays_including_queue"] == 12
    # Starting later does not make the load ahead disappear: the line has been working on it meanwhile.
    later = estimate_in_house(800, start_date="2026-04-20")
    assert later["completion_date"] == "2026-06-01"
    assert [s["open_order_workdays"] for s in later["stages"]] == [0, 28, 24, 35]
    # The order statuses are only known on 1 April, so an earlier start date is not loaded.
    before = estimate_in_house(800, start_date="2026-03-20")
    assert before["queue_basis"] == "not_applied_before_snapshot" and "open_order_load" not in before


def test_explicit_plan_uses_the_same_in_house_queue():
    plan = estimate_production_plan("TOPS", 800, 500, [{"workshop_id": "W1", "pieces": 300}])
    in_house = next(b for b in plan["branches"] if b["producer"] == "IN_HOUSE")
    assert in_house == estimate_in_house(500)
    assert plan["completion_date"] == in_house["completion_date"] == "2026-05-30"


def test_fastest_plan_goes_outside_when_in_house_is_booked():
    plan = optimize_fastest_plan("TOPS", 800)
    assert plan["completion_date"] == "2026-04-06" and plan["in_house_pieces"] == 0
    assert sum(a["pieces"] for a in plan["allocations"]) == 800
    old = optimize_fastest_plan("TOPS", 800, in_house_queue_workdays=0)
    assert old["in_house_pieces"] == 476 and old["completion_date"] == "2026-04-04"


def test_cheapest_plan_compares_outside_workshops_unless_an_in_house_cost_is_given():
    plan = optimize_cheapest_plan("TOPS", 800, 25)
    assert plan["status"] == "ok" and plan["in_house_pieces"] == 0 and plan["include_in_house"] is False
    assert plan["allocations"] == [{"workshop_id": "W3", "pieces": 800}]
    assert plan["external_processing_cost"] == 640.0
    assert any("left out" in a for a in plan["assumptions"])
    # Asking for in-house without a cost does not quietly price it at zero.
    asked = optimize_cheapest_plan("TOPS", 800, 25, include_in_house=True)
    assert asked["status"] == "needs_assumption" and "in_house_cost_per_piece" in asked["message"]
    # With a stated cost, in-house competes at that cost; 25 days is too soon for it, 70 days is not.
    assert optimize_cheapest_plan("TOPS", 800, 25, in_house_cost_per_piece=0.5)["in_house_pieces"] == 0
    priced = optimize_cheapest_plan("TOPS", 800, 70, in_house_cost_per_piece=0.5)
    assert priced["in_house_pieces"] == 800 and priced["completion_date"] == "2026-06-01"
    assert (priced["in_house_cost_assumed"], priced["total_cost_with_assumed_in_house"]) == (400.0, 400.0)
    # Turning in-house off explicitly wins over a stated cost.
    assert optimize_cheapest_plan("TOPS", 800, 70, include_in_house=False, in_house_cost_per_piece=0.5)["in_house_pieces"] == 0


def test_cheapest_plan_says_when_outside_workshops_cannot_make_it():
    result = optimize_cheapest_plan("ACCESSORIES", 5000, 14)
    assert result["status"] == "infeasible" and "fastest plan" in result["message"]


@pytest.mark.parametrize("cost", [-1, 1001, float("nan"), "0.5", True])
def test_in_house_cost_must_be_a_plain_number(cost):
    assert optimize_cheapest_plan("TOPS", 800, 70, in_house_cost_per_piece=cost)["status"] == "error"


def test_tool_descriptions_tell_the_model_how_the_queue_and_cost_work():
    specs = {t["function"]["name"]: t["function"] for t in TOOLS}
    queue = specs["estimate_in_house"]["parameters"]["properties"]["queue_workdays"]["description"]
    assert "unfinished orders" in queue and "upper bound" in queue
    cheapest = specs["optimize_cheapest_plan"]["parameters"]["properties"]
    assert "Never invent" in cheapest["in_house_cost_per_piece"]["description"]
    assert "\n" not in specs["estimate_in_house"]["description"]
