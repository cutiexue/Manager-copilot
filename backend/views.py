"""Read-only views behind the HTTP API: one order, one stage's output, a feasibility estimate and
one cited source row (plan §11). They call the agent's own tools, so the API and the chat agree,
and return evidence in the same {refs, rows} shape as a chat turn.
"""

import json
import re
from datetime import date

import evidence_refs
from data_loader import STAGES, load_production, production_row_numbers
from llm import execute_tool
from rules import MAX_BASELINE_WORKDAYS, SNAPSHOT, is_workday, previous_workdays
from tool_schemas import ESTIMATION_FUNCTIONS, TOOLS
from tools import compare_stage_output, trace_order

MAX_SERIES_WORKDAYS = MAX_BASELINE_WORKDAYS


class NotFoundError(LookupError):
    """Nothing matches; `candidates` lists close matches the client can offer instead."""

    def __init__(self, message, candidates=()):
        super().__init__(message)
        self.candidates = list(candidates)


def _evidence(result):
    refs = evidence_refs.collect(result)
    return {"refs": refs, "rows": evidence_refs.raw_rows(refs)}


def order_detail(order_id, actions):
    """The order with its computed facts and cited rows, and the follow-ups saved for it."""
    trace = trace_order(order_id)
    if trace["status"] != "ok":
        raise NotFoundError(f"No order {order_id.strip()!r} in the data.", trace.get("candidates", ()))
    wanted = trace["data"]["order_id"]
    return {
        "order_id": wanted,
        "trace": trace,
        "evidence": _evidence(trace),
        "follow_ups": {
            "notes": actions.list_notes(wanted),
            "reminders": [r for r in actions.list_reminders()
                          if r.get("order_id") == wanted and r["status"] != "DISMISSED"],
            "watches": [w for w in actions.list_watches() if w.get("order_id") == wanted],
        },
    }


def _bounded(name, value, highest):
    if type(value) is not int or not 1 <= value <= highest:
        raise ValueError(f"{name} must be a whole number from 1 to {highest}.")
    return value


def latest_production_day():
    """The last workday before the snapshot date: the newest day with recorded output."""
    return previous_workdays(date.fromisoformat(SNAPSHOT), 1)[0]


def stage_output(stage, on=None, baseline_days=7, days=10):
    """One stage's output on a day (default: the last workday) against its baseline, plus the
    daily series up to that day."""
    name = stage.strip().upper() if isinstance(stage, str) else ""
    if name not in STAGES:
        raise ValueError(f"Unknown stage {stage!r}; use {', '.join(STAGES)}.")
    try:
        day = latest_production_day() if on is None else date.fromisoformat(on)
    except (TypeError, ValueError):
        raise ValueError("date must be YYYY-MM-DD.") from None
    _bounded("baseline_days", baseline_days, MAX_BASELINE_WORKDAYS)
    _bounded("days", days, MAX_SERIES_WORKDAYS)

    comparison = compare_stage_output(name, day.isoformat(), baseline_days)
    if comparison["status"] == "error":
        raise ValueError(comparison["message"])
    if comparison["status"] == "not_found":
        raise NotFoundError(comparison["message"])

    # Oldest first; a workday with no record stays in the series as None (missing is not zero).
    dates = sorted(previous_workdays(day, days - 1 if is_workday(day) else days))
    if is_workday(day):
        dates.append(day)
    output = {(r["date"], r["stage"]): int(r["pieces_completed"]) for r in load_production()}
    rows = production_row_numbers()
    series = [{"date": d.isoformat(), "stage": name,
               "pieces_completed": output.get((d.isoformat(), name)),
               "source_row": rows.get((d.isoformat(), name))} for d in dates]
    return {"status": comparison["status"], "stage": name, "date": day.isoformat(),
            "comparison": comparison, "series": series,
            "evidence": _evidence({"comparison": comparison, "series": series})}


def estimators():
    """The feasibility estimators the API runs, with the argument schema each one accepts."""
    return [{"name": tool["function"]["name"], "description": tool["function"]["description"],
             "parameters": tool["function"]["parameters"]}
            for tool in TOOLS if tool["function"]["name"] in ESTIMATION_FUNCTIONS]


def estimate(estimator, arguments):
    """Run one read-only feasibility estimator with the same argument checks the agent gets."""
    if estimator not in ESTIMATION_FUNCTIONS:
        raise ValueError(f"Unknown estimator {estimator!r}; use one of: {', '.join(ESTIMATION_FUNCTIONS)}.")
    if not isinstance(arguments, dict):
        raise ValueError("arguments must be an object.")
    result = execute_tool(estimator, json.dumps(arguments))
    if result.get("status") == "error":
        message = result.get("message", "")
        if message.startswith("Internal tool error") or message == "Could not read the factory data.":
            raise RuntimeError(f"{estimator} failed: {message}")  # logged and reported as a 500
        raise ValueError(message)
    return {"estimator": estimator, "result": result, "evidence": _evidence(result)}


_EVIDENCE_ID = re.compile(r"([a-z_]+\.csv):([0-9]{1,7})")


def evidence_row(evidence_id):
    """One cited CSV row by its ID, "<file>:<line>" such as "orders.csv:12" (the header is line 1)."""
    match = _EVIDENCE_ID.fullmatch(evidence_id.strip())
    found = evidence_refs.lookup(match.group(1), int(match.group(2))) if match else None
    if found is None:
        raise NotFoundError(f"No source row {evidence_id!r}. IDs look like orders.csv:12 "
                            "(file name and line number; the header is line 1).")
    return found
