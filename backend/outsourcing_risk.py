"""Quality and delivery risk of sending work to outside workshops, from workshops.csv.

The data dictionary defines defect_rate as the chance that a batch comes back defective and is partly
redone, and gives each workshop a one-line note "a human dispatcher would give it". Risk is therefore
told batch by batch: a rework at one workshop delays only that workshop's pieces, never the others.

- each workshop's profile: defect rate, the dispatcher's note word for word, and rule-based flags;
- each batch: its chance of needing rework, its pieces, and the latest those pieces could arrive if
  reworked;
- the plan: the chance every batch comes back clean, the pieces expected to sit in reworked batches,
  and, with a deadline, how many pieces could miss it and how likely that is.

How long a partial rework takes is not in the data, so "the latest those pieces could arrive" is a
stated upper bound: the whole batch redone once at the same workshop, with no new queue, then shipped
again. Real reworks are partial, so they finish sooner. In-house work has no defect data and is left out.
"""

from datetime import date, timedelta
from decimal import Decimal
from math import ceil, prod

from data_loader import WORKSHOPS_SOURCE, load_workshops, source_ref, workshop_row_numbers
from rules import (BUSY_QUEUE_DAYS, HIGH_DEFECT_RATE, RISK_HIGH_FROM, RISK_MEDIUM_FROM,
                   SLOW_PICKUP_DAYS)

REWORK_ASSUMPTION = ("How long a partial rework takes is not in the data. The latest arrival of a reworked "
                     "batch assumes the whole batch is redone once at the same workshop with no new queue, then "
                     "shipped again, so it is an upper bound; real reworks are partial and finish sooner.")


def _workday_finish(start, workdays):
    """The date the last of `workdays` Monday-to-Saturday workdays ends, counting `start` as day one."""
    current, left = start, workdays
    while True:
        if current.weekday() != 6:
            left -= 1
            if left <= 0:
                return current
        current += timedelta(days=1)


def workshop_profile(row):
    """What a dispatcher should know about one workshop before sending it work."""
    flags = []
    defect = float(row["defect_rate"])
    if row["status"] != "ACTIVE":
        flags.append(f"{row['status'].lower()}: may not take new work")
    if defect >= HIGH_DEFECT_RATE:
        flags.append(f"high defect rate ({defect:.0%} of batches)")
    if int(row["pickup_lead_days"]) >= SLOW_PICKUP_DAYS:
        flags.append(f"slow pickup and delivery ({row['pickup_lead_days']} days each way)")
    if float(row["current_queue_days"]) >= BUSY_QUEUE_DAYS:
        flags.append(f"busy: {row['current_queue_days']} days of work already queued")
    if row["max_batch_pieces"]:
        flags.append(f"on trial: batches of at most {row['max_batch_pieces']} pieces")
    return {"workshop_id": row["workshop_id"], "name": row["name"], "defect_rate": defect,
            "dispatcher_note": row["notes"], "flags": flags,
            "source": source_ref(WORKSHOPS_SOURCE, workshop_row_numbers()[row["workshop_id"]], row["workshop_id"])}


def _redo_completion(batch, row):
    """When a batch would arrive if it came back defective and were redone in full once."""
    redo_workdays = ceil(Decimal(batch["pieces"]) / Decimal(row["capacity_pieces_per_day"]))
    back = date.fromisoformat(batch["completion_date"]) + timedelta(days=1)
    return _workday_finish(back, redo_workdays) + timedelta(days=int(row["pickup_lead_days"]))


def _level(chance):
    return "high" if chance >= RISK_HIGH_FROM else "medium" if chance >= RISK_MEDIUM_FROM else "low"


# How a plan is rated for the manager, from its risk level.
STRATEGY_RATING = {"high": "High-risk strategy", "medium": "Medium-risk strategy", "low": "Low-risk strategy"}


def _day(iso):
    return f"{date.fromisoformat(iso):%d %b}".lstrip("0")


def plan_risk(batches, deadline=None):
    """Risk of a plan's outsourced batches, told batch by batch.

    batches: [{"workshop_id" (or "producer"), "pieces", "completion_date"}], one per workshop used.
    deadline: an ISO date the plan must meet, or None.
    """
    rows = {row["workshop_id"]: row for row in load_workshops()}
    used = [b for b in batches if b.get("pieces")]
    if not used:
        return {"status": "no_outsourcing", "message": "No work goes to outside workshops, so no workshop risk applies."}
    entries = []
    for batch in used:
        row = rows[batch.get("workshop_id") or batch["producer"]]
        entry = {**workshop_profile(row), "pieces": batch["pieces"], "completion_date": batch["completion_date"],
                 "rework_chance": float(row["defect_rate"]),
                 "latest_arrival_if_reworked": _redo_completion(batch, row).isoformat()}
        if deadline:
            entry["late_if_reworked"] = entry["latest_arrival_if_reworked"] > deadline
        entries.append(entry)
    total = sum(e["pieces"] for e in entries)
    clean = prod(1 - e["rework_chance"] for e in entries)
    expected = sum(e["rework_chance"] * e["pieces"] for e in entries)
    result = {
        "status": "ok",
        "batches": len(entries),
        "outsourced_pieces": total,
        "chance_all_batches_clean": round(clean, 4),
        "chance_some_batch_needs_rework": round(1 - clean, 4),
        "expected_pieces_in_reworked_batches": round(expected, 1),
        "workshops": entries,
        "assumptions": [
            "Each workshop's batch needs rework independently, with its defect_rate from workshops.csv.",
            "A rework delays only that workshop's pieces; other batches arrive as planned.",
            REWORK_ASSUMPTION,
            "In-house work has no defect data and is not included.",
        ],
    }
    lines = [f"{clean:.0%} chance every outsourced batch comes back clean."]
    if deadline is None:
        for e in entries:
            lines.append(f"{e['workshop_id']} {e['name']} ({e['pieces']} pieces): {e['rework_chance']:.0%} chance of "
                         f"rework; if so, those pieces arrive by {_day(e['latest_arrival_if_reworked'])} at the latest "
                         f"instead of {_day(e['completion_date'])}.")
        result.update(risk_level=_level(1 - clean), risk_basis="chance that some outsourced batch needs rework")
    else:
        exposed = [e for e in entries if e["late_if_reworked"]]
        on_time = prod(1 - e["rework_chance"] for e in exposed)
        result.update(
            deadline_date=deadline,
            pieces_that_could_be_late=sum(e["pieces"] for e in exposed),
            chance_some_pieces_late=round(1 - on_time, 4),
            chance_all_pieces_on_time=round(on_time, 4),
            risk_level=_level(1 - on_time),
            risk_basis="chance that a rework pushes some pieces past the deadline (upper-bound rework time)",
        )
        if not exposed:
            lines.append(f"Even if a batch needs rework, all {total} outsourced pieces still arrive by the "
                         f"{_day(deadline)} deadline.")
        for e in exposed:
            others = total - e["pieces"]
            lines.append(f"{e['workshop_id']} {e['name']} ({e['pieces']} pieces): {e['rework_chance']:.0%} chance of "
                         f"rework; if so, those pieces could arrive as late as {_day(e['latest_arrival_if_reworked'])}, "
                         f"after the {_day(deadline)} deadline" + (f"; the other {others} pieces are unaffected." if others else "."))
    lines.append("Rework time is not in the data; the latest dates assume the whole batch is redone, so real "
                 "delays are shorter.")
    result["strategy_rating"] = STRATEGY_RATING[result["risk_level"]]
    if result["risk_level"] == "high":
        # Name what drives the risk, so a safer plan can avoid it.
        drivers = sorted(entries, key=lambda e: e["rework_chance"] * e["pieces"], reverse=True)
        result["risk_drivers"] = [e["workshop_id"] for e in drivers
                                  if deadline is None or e.get("late_if_reworked")][:3]
    result["summary"] = f"{result['strategy_rating']}. " + " ".join(lines)
    return result
