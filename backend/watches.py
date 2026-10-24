"""Standing watches over orders, checked against scripted data snapshots.

The course CSVs never change, so a watch would never fire on them. As the slides state, watches
are demonstrated on versioned snapshots: each version in track1/scenarios/watch_snapshots.json
applies scripted order updates on top of the 2026-04-01 course data for one later day. Only the
watch checker reads them; every other tool keeps using the course data. The snapshot in use is
kept in the app database, so a restart does not lose it.
"""

import json
from datetime import date
from functools import lru_cache
from pathlib import Path

from data_loader import STAGES, load_orders
from rules import SNAPSHOT

SNAPSHOT_FILE = Path(__file__).resolve().parent / "track1" / "scenarios" / "watch_snapshots.json"
BASE_VERSION = "v0"
CONDITIONS = ("not_moved_by", "becomes_overdue", "completed", "reaches_stage")
_CHANGEABLE = {"status", "current_stage", "last_activity_date", "completed_date", "days_late"}


@lru_cache(maxsize=1)
def load_snapshots():
    """The scripted versions, validated once: v0 is the course data and dates only move forward."""
    versions = json.loads(SNAPSHOT_FILE.read_text(encoding="utf-8"))["versions"]
    if not versions or versions[0]["version"] != BASE_VERSION or versions[0]["date"] != SNAPSHOT or versions[0]["changes"]:
        raise ValueError("The first snapshot must be the unchanged course data.")
    known = {order["order_id"] for order in load_orders()}
    previous = None
    for version in versions:
        day = date.fromisoformat(version["date"])
        if previous and day <= previous:
            raise ValueError("Snapshot dates must increase.")
        previous = day
        for change in version["changes"]:
            if change.get("order_id") not in known or not set(change) - {"order_id"} <= _CHANGEABLE:
                raise ValueError(f"Invalid scripted change in {version['version']}: {change}")
    return tuple(versions)


def version_info(version_id):
    for version in load_snapshots():
        if version["version"] == version_id:
            return {key: version[key] for key in ("version", "date", "label")}
    raise ValueError(f"Unknown data snapshot {version_id}.")


def next_version(version_id):
    ids = [version["version"] for version in load_snapshots()]
    index = ids.index(version_info(version_id)["version"])
    return ids[index + 1] if index + 1 < len(ids) else None


def order_state(order_id, version_id):
    """The order as a snapshot shows it: course data plus every scripted change up to that version."""
    state = next((dict(order) for order in load_orders() if order["order_id"] == order_id), None)
    if state is None:
        return None
    for version in load_snapshots():
        for change in version["changes"]:
            if change["order_id"] == order_id:
                state.update({key: value for key, value in change.items() if key != "order_id"})
        if version["version"] == version_id:
            break
    return state


def baseline(state):
    """What a watch remembers about its order when it starts."""
    return {key: state[key] for key in ("status", "current_stage", "last_activity_date", "due_date", "customer")}


def describe(condition, order_id, deadline=None, stage=None):
    if condition == "not_moved_by":
        return f"Alert if {order_id} has not moved by {deadline}"
    if condition == "becomes_overdue":
        return f"Alert when {order_id} becomes overdue"
    if condition == "completed":
        return f"Alert when {order_id} is complete"
    return f"Alert when {order_id} reaches {stage}"


def check_definition(condition, state, data_date, deadline=None, stage=None):
    """Validate a watch against the order's current state; returns (deadline, stage) to store."""
    if condition not in CONDITIONS:
        raise ValueError(f"condition must be one of {', '.join(CONDITIONS)}.")
    order_id = state["order_id"]
    if condition == "not_moved_by":
        if not deadline:
            raise ValueError("not_moved_by needs a deadline date (YYYY-MM-DD).")
        try:
            day = date.fromisoformat(deadline)
        except (TypeError, ValueError):
            raise ValueError("deadline must be a date in YYYY-MM-DD format.") from None
        if day < data_date:
            raise ValueError(f"The deadline {deadline} is before the current data date {data_date.isoformat()}.")
        deadline, stage = day.isoformat(), None
    elif condition == "reaches_stage":
        if stage not in STAGES:
            raise ValueError(f"stage must be one of {', '.join(STAGES)}.")
        if state["status"] == "COMPLETE" or STAGES.index(stage) <= _stage_index(state):
            raise ValueError(f"{order_id} is already at {state['current_stage']}; nothing to watch.")
        deadline = None
    else:
        deadline, stage = None, None
    if state["status"] == "COMPLETE":
        raise ValueError(f"{order_id} is already complete; nothing to watch.")
    if condition == "becomes_overdue" and date.fromisoformat(state["due_date"]) < data_date:
        raise ValueError(f"{order_id} is already overdue (due {state['due_date']}).")
    return deadline, stage


def _stage_index(state):
    return len(STAGES) if state["current_stage"] == "COMPLETE" else STAGES.index(state["current_stage"])


def evaluate(watch, version_id):
    """Judge one watch on one snapshot: met, not_met, resolved (can no longer fire) or error."""
    state = order_state(watch["order_id"], version_id)
    if state is None:
        return "error", f"{watch['order_id']} is no longer in the data."
    data_date = date.fromisoformat(version_info(version_id)["date"])
    start = watch["baseline"]
    oid, condition = watch["order_id"], watch["condition"]
    if condition == "not_moved_by":
        moved = (state["status"], state["current_stage"], state["last_activity_date"]) != (
            start["status"], start["current_stage"], start["last_activity_date"])
        if moved:
            return "resolved", (f"{oid} moved: {start['current_stage']} → {state['current_stage']}, "
                                f"last activity {state['last_activity_date']}.")
        if data_date >= date.fromisoformat(watch["deadline"]):
            return "met", (f"{oid} has not moved by {watch['deadline']}: still {state['current_stage']}, "
                           f"last activity {state['last_activity_date']}.")
        return "not_met", f"No change yet; checking until {watch['deadline']}."
    if condition == "completed":
        if state["status"] == "COMPLETE":
            return "met", f"{oid} completed on {state['completed_date']}."
        return "not_met", f"{oid} is at {state['current_stage']}."
    if condition == "becomes_overdue":
        if state["status"] == "COMPLETE":
            return "resolved", f"{oid} completed on {state['completed_date']}."
        if date.fromisoformat(state["due_date"]) < data_date:
            return "met", (f"{oid} is overdue: due {state['due_date']}, still {state['current_stage']} "
                           f"on {data_date.isoformat()}.")
        return "not_met", f"{oid} is due {state['due_date']}."
    if state["status"] == "COMPLETE" or _stage_index(state) >= STAGES.index(watch["stage"]):
        return "met", f"{oid} reached {state['current_stage']} (last activity {state['last_activity_date']})."
    return "not_met", f"{oid} is at {state['current_stage']}."


def check_watches(actions, now):
    """Check every active watch on the current snapshot. Safe to run any number of times: a watch
    fires once, and a check is recorded only when its result or the snapshot changes."""
    version_id = actions.data_version()
    outcomes = []
    for watch in actions.list_watches(status="ACTIVE"):
        result, detail = evaluate(watch, version_id)
        actions.record_watch_check(watch, now, version_id, result, detail)
        outcomes.append({"watch_id": watch["id"], "result": result, "detail": detail})
    return {"data_version": version_info(version_id), "checked": len(outcomes), "outcomes": outcomes}
