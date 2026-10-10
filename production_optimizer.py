"""Optimize integer batch splits under the existing deterministic estimates."""

from datetime import date, timedelta
from decimal import Decimal
from math import ceil

from data_loader import load_workshops
from production_estimates import SNAPSHOT, estimate_in_house, estimate_production_plan


def _prepare(category, total_pieces, start_date, include_in_house, queue, baseline_days):
    if category not in ("TOPS", "ACCESSORIES"):
        raise ValueError("category must be TOPS or ACCESSORIES.")
    if type(total_pieces) is not int or not 1 <= total_pieces <= 1000000:
        raise ValueError("total_pieces must be an integer from 1 to 1000000.")
    if type(include_in_house) is not bool:
        raise ValueError("include_in_house must be a boolean.")
    start = date.fromisoformat(start_date)
    producers = []
    for row in load_workshops():
        if row["status"] != "ACTIVE" or category not in row["makes"].split("+"):
            continue
        producers.append({
            "id": row["workshop_id"], "cost": Decimal(row["cost_per_piece"]),
            "limit": min(total_pieces, int(row["max_batch_pieces"] or total_pieces)),
            "rate": Decimal(row["capacity_pieces_per_day"]),
            "queue": Decimal(row["current_queue_days"]),
            "transport": int(row["pickup_lead_days"]),
        })
    if include_in_house:
        sample = estimate_in_house(1, start_date, queue, baseline_days)
        if sample["status"] != "ok":
            raise ValueError(sample["message"])
        totals = [sum(int(r["pieces_completed"]) for r in sample["baseline_records"]
                      if r["stage"] == stage["stage"]) for stage in sample["stages"]]
        producers.append({"id": "IN_HOUSE", "cost": Decimal(0), "limit": total_pieces,
                          "totals": totals, "baseline_days": baseline_days, "queue": ceil(queue)})
    return start, producers


def _capacity(producer, start, deadline):
    """Find the largest integer quantity deliverable by a date."""
    transport = producer.get("transport", 0)
    last_workday = deadline - timedelta(days=transport)
    count = max(0, (last_workday - start).days + 1)
    weeks, remainder = divmod(count, 7)
    available = weeks * 6 + sum((start.weekday() + i) % 7 != 6 for i in range(remainder))

    def duration(quantity):
        if "totals" in producer:
            return producer["queue"] + sum(
                (quantity * producer["baseline_days"] + total - 1) // total
                for total in producer["totals"])
        return ceil(producer["queue"] + Decimal(quantity) / producer["rate"])

    low, high = 0, producer["limit"]
    while low < high:
        middle = (low + high + 1) // 2
        if duration(middle) <= available:
            low = middle
        else:
            high = middle - 1
    return low


def _allocate(producers, start, deadline, quantity):
    """With independent capacities and linear costs, cheapest units go first."""
    assignments = []
    for producer in sorted(producers, key=lambda p: (p["cost"], p["id"])):
        pieces = min(quantity, _capacity(producer, start, deadline))
        if pieces:
            assignments.append({"workshop_id": producer["id"], "pieces": pieces})
            quantity -= pieces
    return assignments, quantity


def _optimize(category, total_pieces, start_date, include_in_house, queue, baseline_days, days):
    try:
        start, producers = _prepare(category, total_pieces, start_date, include_in_house, queue, baseline_days)
        if days is not None and (type(days) is not int or not 1 <= days <= 3650):
            raise ValueError("deadline_days must be an integer from 1 to 3650.")
        # 第一天包含开始日期，10 天内即开始日期加 9 天。
        horizon = start + timedelta(days=(days or 3650) - 1)
        allocations, missing = _allocate(producers, start, horizon, total_pieces)
        if missing:
            return {"status": "infeasible" if days else "search_limit",
                    "message": "Insufficient modeled capacity within the requested horizon.",
                    "deadline_date": horizon.isoformat(), "unallocated_pieces": missing,
                    "maximum_deliverable_pieces": total_pieces - missing}
        if days is None:
            # 可行性随日期单调变化，二分寻找最早可交付日期。
            low, high = 0, (horizon - start).days
            while low < high:
                middle = (low + high) // 2
                _, missing = _allocate(producers, start, start + timedelta(days=middle), total_pieces)
                if missing:
                    low = middle + 1
                else:
                    high = middle
            horizon = start + timedelta(days=low)
            allocations, _ = _allocate(producers, start, horizon, total_pieces)
        in_house = sum(a["pieces"] for a in allocations if a["workshop_id"] == "IN_HOUSE")
        external = [a for a in allocations if a["workshop_id"] != "IN_HOUSE"]
        result = estimate_production_plan(category, total_pieces, in_house, external,
                                          start_date, queue, baseline_days)
        if result["status"] != "ok":
            return result
        result.update(
            objective="minimum_external_processing_cost_by_deadline" if days else "earliest_completion_then_external_processing_cost",
            optimality="Exact for independent producers, integer quantities, linear external costs and the stated deterministic model.",
            deadline_date=horizon.isoformat() if days else None,
            calendar_days_inclusive=result["elapsed_calendar_days"] + 1,
            allocations=external, in_house_pieces=in_house, include_in_house=include_in_house,
        )
        result["assumptions"] = result["assumptions"] + [
            "One batch per producer; arbitrary numbers of eligible workshops may run in parallel.",
            "In-house processing contributes zero to the external-charge objective, not zero real cost.",
            "No shared-resource contention, split fees or quality-risk optimization is modeled.",
            "Deadline days are inclusive calendar days; the start date is day one.",
            "This is not an existing-order forecast or an on-time probability estimate.",
        ]
        return result
    except (ValueError, TypeError, OverflowError) as exc:
        return {"status": "error", "message": str(exc)}


def optimize_fastest_plan(category, total_pieces, start_date=SNAPSHOT,
                          include_in_house=True, in_house_queue_workdays=0, baseline_days=7):
    """Find earliest full delivery; break date ties by external processing cost."""
    return _optimize(category, total_pieces, start_date, include_in_house,
                     in_house_queue_workdays, baseline_days, None)


def optimize_cheapest_plan(category, total_pieces, deadline_days, start_date=SNAPSHOT,
                           include_in_house=True, in_house_queue_workdays=0, baseline_days=7):
    """Minimize external processing charges within inclusive calendar deadline_days."""
    if deadline_days is None:
        return {"status": "error", "message": "deadline_days is required."}
    return _optimize(category, total_pieces, start_date, include_in_house,
                     in_house_queue_workdays, baseline_days, deadline_days)
