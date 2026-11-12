"""Stage output over a period: totals, workday averages and period-to-period comparisons.

The model must never add daily figures itself or pass a one-day comparison off as a period one
(evaluation Q05, Q06, Q13). These tools do the arithmetic from production_log.csv and say exactly
which days they counted: the factory works Monday to Saturday, Sunday rows are recorded as 0, and a
workday with no record is listed as missing, never counted as zero or silently dropped.
"""

from datetime import date, timedelta

from data_loader import PRODUCTION_SOURCE, STAGES, load_production, production_row_numbers, source_ref
from rules import is_workday, today_iso

MAX_PERIOD_DAYS = 366


def _dates(date_from, date_to):
    try:
        start, end = date.fromisoformat(date_from), date.fromisoformat(date_to)
    except (TypeError, ValueError):
        raise ValueError("Use valid dates in YYYY-MM-DD format.") from None
    if end < start:
        raise ValueError("date_to must not be before date_from.")
    if (end - start).days + 1 > MAX_PERIOD_DAYS:
        raise ValueError(f"A period may cover at most {MAX_PERIOD_DAYS} days.")
    return start, end


def _stages(stage):
    if stage is None:
        return list(STAGES)
    if stage not in STAGES:
        raise ValueError(f"stage must be one of {', '.join(STAGES)}.")
    return [stage]


def _period(stage, start, end, by_key, rows):
    """One stage over one period, with every day it counted."""
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    workdays = [d for d in days if is_workday(d)]
    recorded = [d for d in days if (d.isoformat(), stage) in by_key]
    missing = [d.isoformat() for d in workdays if (d.isoformat(), stage) not in by_key]
    total = sum(int(by_key[(d.isoformat(), stage)]["pieces_completed"]) for d in recorded)
    recorded_workdays = sum(1 for d in recorded if is_workday(d))
    result = {
        "stage": stage, "date_from": start.isoformat(), "date_to": end.isoformat(),
        # A partial sum is not the total for the requested period. Keep the observed sum separately.
        "total_pieces": None if missing else total, "recorded_total_pieces": total,
        "complete_records": not missing,
        "status": "ok" if not missing else ("partial" if recorded_workdays else "insufficient_data"),
        "calendar_days": len(days), "scheduled_workdays": len(workdays),
        "recorded_workdays": recorded_workdays, "missing_workdays": missing,
        "mean_per_recorded_workday": round(total / recorded_workdays, 2) if recorded_workdays else None,
        "source_rows": [source_ref(PRODUCTION_SOURCE, rows[(d.isoformat(), stage)], f"{d.isoformat()} {stage}")
                        for d in recorded],
    }
    if not missing and workdays:
        result["mean_per_scheduled_workday"] = round(total / len(workdays), 2)
    return result


def summarize_stage_output(date_from, date_to, stage=None):
    """Total and per-workday average output of one stage (or all four) over a date range."""
    try:
        start, end = _dates(date_from, date_to)
        stages = _stages(stage)
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}
    records = load_production()
    by_key = {(r["date"], r["stage"]): r for r in records}
    rows = production_row_numbers()
    periods = [_period(s, start, end, by_key, rows) for s in stages]
    missing = any(p["missing_workdays"] for p in periods)
    return {
        "status": ("ok" if not missing else
                   "partial" if any(p["recorded_workdays"] for p in periods) else "insufficient_data"),
        "date_from": start.isoformat(), "date_to": end.isoformat(),
        "stages": periods, "source": PRODUCTION_SOURCE,
        "rules": "Workdays are Monday to Saturday; Sunday rows are recorded as 0 and add nothing. A workday "
                 "without a record is listed in missing_workdays, never counted as zero.",
        "warnings": ["Factory-wide stage output, not per-order progress or capacity."] + (
            ["Some workdays have no record; total_pieces is unknown for those stages. "
             "recorded_total_pieces covers recorded days only, not the full period."] if missing else []),
    }


def _last_complete_weeks(today):
    """The two most recent complete Monday-to-Sunday weeks that end before today."""
    last_sunday = today - timedelta(days=today.weekday() + 1)
    second = (last_sunday - timedelta(days=6), last_sunday)
    first = (second[0] - timedelta(days=7), second[0] - timedelta(days=1))
    return first, second


def compare_stage_periods(first_from=None, first_to=None, second_from=None, second_to=None, stage=None):
    """Compare stage totals between two periods; with no dates, the two most recent complete calendar weeks."""
    try:
        given = [first_from, first_to, second_from, second_to]
        if any(given) and not all(given):
            raise ValueError("Give all four dates, or none for the two most recent complete calendar weeks.")
        if all(given):
            first, second = _dates(first_from, first_to), _dates(second_from, second_to)
            basis = "periods given"
        else:
            first, second = _last_complete_weeks(date.fromisoformat(today_iso()))
            basis = "the two most recent complete Monday-to-Sunday weeks before today's data date"
        stages = _stages(stage)
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}
    records = load_production()
    by_key = {(r["date"], r["stage"]): r for r in records}
    rows = production_row_numbers()
    comparisons = []
    for s in stages:
        a, b = _period(s, *first, by_key, rows), _period(s, *second, by_key, rows)
        comparable = a["complete_records"] and b["complete_records"]
        change = b["total_pieces"] - a["total_pieces"] if comparable else None
        comparisons.append({
            "stage": s, "first_total": a["total_pieces"], "second_total": b["total_pieces"], "change": change,
            "change_percent": round(100 * change / a["total_pieces"], 2) if comparable and a["total_pieces"] else None,
            "first_recorded_total": a["recorded_total_pieces"], "second_recorded_total": b["recorded_total_pieces"],
            "comparable": comparable,
            "status": ("ok" if comparable else "insufficient_data"
                       if not a["recorded_workdays"] or not b["recorded_workdays"] else "partial"),
            "first_missing_workdays": a["missing_workdays"], "second_missing_workdays": b["missing_workdays"],
            "source_rows": a["source_rows"] + b["source_rows"],
        })
    complete = not any(c["first_missing_workdays"] or c["second_missing_workdays"] for c in comparisons)
    # A global "largest" claim needs every requested stage to be comparable.
    ranked = [c for c in comparisons if c["change_percent"] is not None] if complete else []
    declines = [c for c in ranked if c["change_percent"] < 0]
    increases = [c for c in ranked if c["change_percent"] > 0]
    return {
        "status": ("ok" if complete else "insufficient_data"
                   if all(c["status"] == "insufficient_data" for c in comparisons) else "partial"), "basis": basis,
        "first_period": {"date_from": first[0].isoformat(), "date_to": first[1].isoformat()},
        "second_period": {"date_from": second[0].isoformat(), "date_to": second[1].isoformat()},
        "stages": comparisons,
        "largest_decline": min(declines, key=lambda c: c["change_percent"])["stage"] if declines else None,
        "largest_increase": max(increases, key=lambda c: c["change_percent"])["stage"] if increases else None,
        "complete_records": complete, "source": PRODUCTION_SOURCE,
        "warnings": ["A change in output is not a diagnosis of its cause."] + (
            [] if complete else ["Stages with missing workdays have unknown period totals and no change "
                                 "or ranking; recorded totals alone are not comparable. Overall largest-change "
                                 "rankings are withheld until every requested stage has complete records."]),
    }
