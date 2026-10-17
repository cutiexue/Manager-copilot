"""Evaluate explicitly assigned new batches, without optimizing or dispatching."""

from datetime import date, timedelta
from decimal import Decimal
from math import ceil, isfinite

from data_loader import load_production, load_workshops

SNAPSHOT = "2026-04-01"
STAGES = ("KNITTING", "ASSEMBLY", "WASHING", "PACKING")
ASSUMPTIONS = [
    "New batches only; each branch delivers finished goods and runs in parallel.",
    "Monday to Saturday are workdays for all producers; no holidays are modeled.",
    "The start date is inclusive: one workday starting Monday finishes Monday.",
    "External queue and production are rounded up together to whole workdays; transport is added once as calendar days after production.",
    "No rework is modeled; defect probability alone does not specify rework duration or cost.",
    "Reported cost includes external per-piece processing charges only. In-house cost is excluded by request; transport and rework charges are not supplied.",
    "Currency is unspecified in the source data.",
]


def _error(message):
    return {"status": "error", "message": message}


def _validate(pieces, start_date):
    if type(pieces) is not int or pieces < 0:
        raise ValueError("pieces must be a nonnegative integer.")
    return date.fromisoformat(start_date)


def _finish(start, workdays):
    if workdays == 0:
        return start
    current = start
    remaining = workdays
    while True:
        if current.weekday() != 6:
            remaining -= 1
            if remaining == 0:
                return current
        current += timedelta(days=1)


def estimate_in_house(pieces, start_date=SNAPSHOT, queue_workdays=0, baseline_days=7):
    """Estimate sequential full-batch stages from recent observed workday output."""
    try:
        start = _validate(pieces, start_date)
        if type(baseline_days) is not int or not 1 <= baseline_days <= 90:
            raise ValueError("baseline_days must be an integer from 1 to 90.")
        if type(queue_workdays) not in (int, float) or not isfinite(queue_workdays) or queue_workdays < 0:
            raise ValueError("queue_workdays must be a finite nonnegative number.")
    except (ValueError, TypeError) as exc:
        return _error(str(exc))
    assumptions = [
        "In-house cost is excluded by request.",
        "The batch receives the full historical average stage throughput; this is not verified free capacity.",
        "Each whole batch finishes one stage before starting the next; no within-batch overlap.",
        f"In-house queue is assumed to be {queue_workdays} workdays; zero means immediate availability.",
        "Historical means are scenario rates, not fixed daily capacity or a guaranteed completion date.",
    ]
    stage_results = []
    evidence = []
    if pieces:
        cursor = min(start, date.fromisoformat(SNAPSHOT)) - timedelta(days=1)
        days = []
        while len(days) < baseline_days:
            if cursor.weekday() != 6:
                days.append(cursor.isoformat())
            cursor -= timedelta(days=1)
        records = load_production()
        for stage in STAGES:
            values = []
            for day in days:
                matches = [r for r in records if r["stage"] == stage and r["date"] == day]
                if len(matches) != 1:
                    return {"status": "insufficient_data", "message": f"Need one output record for {stage} on {day}."}
                value = int(matches[0]["pieces_completed"])
                if value < 0:
                    return _error("Historical output cannot be negative.")
                values.append(value)
                evidence.append(matches[0].copy())
            total = sum(values)
            if total == 0:
                return {"status": "insufficient_data", "message": f"Zero historical throughput for {stage}."}
            stage_results.append({"stage": stage, "average_pieces_per_workday": total / baseline_days,
                                  "production_workdays": (pieces * baseline_days + total - 1) // total})
    duration = ceil(queue_workdays) + sum(s["production_workdays"] for s in stage_results) if pieces else 0
    return {"status": "ok", "producer": "IN_HOUSE", "pieces": pieces,
            "workdays_including_queue": duration, "completion_date": _finish(start, duration).isoformat(),
            "cost_included": False, "stages": stage_results, "baseline_records": evidence,
            "assumptions": ASSUMPTIONS + assumptions, "source": "track1/data/production_log.csv"}


def _estimate_workshop(workshop_id, category, pieces, start_date=SNAPSHOT):
    try:
        start = _validate(pieces, start_date)
    except (TypeError, ValueError) as exc:
        return _error(str(exc))
    if category not in ("TOPS", "ACCESSORIES"):
        return _error("category must be TOPS or ACCESSORIES.")
    workshop = next((r for r in load_workshops() if r["workshop_id"] == workshop_id), None)
    if workshop is None:
        return _error("Unknown workshop ID.")
    if pieces:
        if workshop["status"] != "ACTIVE":
            return _error(f"{workshop_id} is not ACTIVE and cannot accept new work.")
        if category not in workshop["makes"].split("+"):
            return _error(f"{workshop_id} cannot make {category}.")
        if workshop["max_batch_pieces"] and pieces > int(workshop["max_batch_pieces"]):
            return _error(f"{workshop_id} exceeds its per-batch cap of {workshop['max_batch_pieces']}.")
    capacity = Decimal(workshop["capacity_pieces_per_day"])
    production_days = Decimal(pieces) / capacity
    workdays = ceil(Decimal(workshop["current_queue_days"]) + production_days) if pieces else 0
    transport = int(workshop["pickup_lead_days"]) if pieces else 0
    completion = _finish(start, workdays) + timedelta(days=transport)
    cost = Decimal(pieces) * Decimal(workshop["cost_per_piece"])
    return {"status": "ok", "producer": workshop_id, "name": workshop["name"], "pieces": pieces,
            "production_workdays_unrounded": float(production_days), "workdays_including_queue": workdays,
            "transport_calendar_days": transport, "completion_date": completion.isoformat(),
            "external_processing_cost": float(cost), "currency": None, "profile": workshop.copy(),
            "snapshot_date": SNAPSHOT, "source": "track1/data/workshops.csv",
            "assumptions": ASSUMPTIONS + ["Queue and profile values use the 2026-04-01 snapshot even for other scenario dates."]}


def estimate_quickstitch(category, pieces, start_date=SNAPSHOT):
    """Estimate W1 QuickStitch."""
    return _estimate_workshop("W1", category, pieces, start_date)


def estimate_steadyhands(category, pieces, start_date=SNAPSHOT):
    """Estimate W2 SteadyHands."""
    return _estimate_workshop("W2", category, pieces, start_date)


def estimate_budgetworks(category, pieces, start_date=SNAPSHOT):
    """Estimate W3 BudgetWorks."""
    return _estimate_workshop("W3", category, pieces, start_date)


def estimate_little_loom(category, pieces, start_date=SNAPSHOT):
    """Estimate W4 Little Loom."""
    return _estimate_workshop("W4", category, pieces, start_date)


def estimate_giantweave(category, pieces, start_date=SNAPSHOT):
    """Estimate W5 GiantWeave."""
    return _estimate_workshop("W5", category, pieces, start_date)


def estimate_nimble_needle(category, pieces, start_date=SNAPSHOT):
    """Estimate W6 Nimble Needle."""
    return _estimate_workshop("W6", category, pieces, start_date)


def estimate_oldmill(category, pieces, start_date=SNAPSHOT):
    """Check W7 OldMill eligibility before estimating."""
    return _estimate_workshop("W7", category, pieces, start_date)


def estimate_freshstart(category, pieces, start_date=SNAPSHOT):
    """Estimate W8 FreshStart with its per-batch cap."""
    return _estimate_workshop("W8", category, pieces, start_date)


WORKSHOP_ESTIMATORS = dict(zip(
    (f"W{i}" for i in range(1, 9)),
    (estimate_quickstitch, estimate_steadyhands, estimate_budgetworks, estimate_little_loom,
     estimate_giantweave, estimate_nimble_needle, estimate_oldmill, estimate_freshstart),
))


def estimate_production_plan(category, total_pieces, in_house_pieces, allocations,
                             start_date=SNAPSHOT, in_house_queue_workdays=0, baseline_days=7):
    """Summarize an explicit allocation; reject gaps rather than allocating them."""
    try:
        start = _validate(total_pieces, start_date)
        _validate(in_house_pieces, start_date)
    except (ValueError, TypeError) as exc:
        return _error(str(exc))
    if category not in ("TOPS", "ACCESSORIES"):
        return _error("category must be TOPS or ACCESSORIES.")
    if total_pieces == 0 or not isinstance(allocations, list):
        return _error("Provide a positive total_pieces and an allocations list.")
    seen = set()
    assigned = in_house_pieces
    for allocation in allocations:
        if not isinstance(allocation, dict) or set(allocation) != {"workshop_id", "pieces"}:
            return _error("Each allocation must contain workshop_id and pieces only.")
        wid, quantity = allocation["workshop_id"], allocation["pieces"]
        if not isinstance(wid, str) or wid not in WORKSHOP_ESTIMATORS or wid in seen:
            return _error("Use known, unique workshop IDs W1 through W8.")
        if type(quantity) is not int or quantity < 0:
            return _error("Allocated quantities must be nonnegative integers.")
        seen.add(wid)
        assigned += quantity
    if assigned != total_pieces:
        return {"status": "invalid_allocation", "message": "Assigned quantities must equal total_pieces.",
                "unallocated_pieces": total_pieces - assigned}
    branches = []
    for allocation in allocations:
        result = WORKSHOP_ESTIMATORS[allocation["workshop_id"]](category, allocation["pieces"], start_date)
        if result["status"] != "ok":
            return {"status": "infeasible", "producer": allocation["workshop_id"], "detail": result}
        if allocation["pieces"]:
            branches.append(result)
    if in_house_pieces:
        result = estimate_in_house(in_house_pieces, start_date, in_house_queue_workdays, baseline_days)
        if result["status"] != "ok":
            return result
        branches.append(result)
    completion = max(r["completion_date"] for r in branches)
    cost = sum((Decimal(str(r.get("external_processing_cost", 0))) for r in branches), Decimal(0))
    return {"status": "ok", "start_date": start_date, "completion_date": completion,
            "elapsed_calendar_days": (date.fromisoformat(completion) - start).days,
            "external_processing_cost": float(cost), "in_house_cost_excluded": True, "currency": None,
            "total_pieces": total_pieces, "branches": branches, "assumptions": ASSUMPTIONS,
            "snapshot_date": SNAPSHOT}
