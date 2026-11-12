"""Operational rules for the Track 1 co-pilot, as inspectable code.

Every judgement the system makes — what counts as overdue, quiet, at risk, or
an unusual drop in output — is defined here with its threshold, so the
definitions can be audited and tested instead of living inside a prompt.
Thresholds are provisional project choices, not validated business standards.
All rules evaluate against the dataset snapshot date; other dates are
scenarios, not facts.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, timedelta

SNAPSHOT = "2026-04-01"  # the course data date (snapshot v0)

# The data the app is looking at now: the course data (v0) until the manager loads a scripted snapshot
# (track1/scenarios/watch_snapshots.json), then that snapshot. ActionStore keeps this in step with the
# version saved in SQLite; every business rule reads "today" from here.
_current = {"version": "v0", "date": SNAPSHOT}
_request_data = ContextVar("request_data_snapshot", default=None)


def set_current_data(version, day):
    # Replace the pair atomically; an in-flight request keeps its own immutable pair.
    global _current
    _current = {"version": version, "date": day}


@contextmanager
def data_context(version=None, day=None):
    """Pin business reads to one snapshot for a request, including tool worker threads.

    LangChain propagates ContextVars to its tool executor. Updating the app's selected
    snapshot affects subsequent requests, never the request already running here.
    """
    selected = dict(_request_data.get() or _current)
    if version is not None or day is not None:
        if version is None or day is None:
            raise ValueError("A data context needs both version and date.")
        selected = {"version": version, "date": day}
    token = _request_data.set(selected)
    try:
        yield dict(selected)
    finally:
        _request_data.reset(token)


def current_version():
    return (_request_data.get() or _current)["version"]


def today_iso():
    """Today for business facts: the date of the data currently loaded (2026-04-01 for the course data)."""
    return (_request_data.get() or _current)["date"]

# The factory works Monday to Saturday and is closed on Sundays.
REST_WEEKDAY = 6

# An IN_PROGRESS order with no recorded activity for at least this many
# calendar days counts as "gone quiet".
QUIET_ORDER_DAYS = 7

# An IN_PROGRESS order due within this many calendar days (inclusive) counts
# as "due soon" when assessing risk.
DUE_SOON_DAYS = 3

# Discovery: for each stage, compare the mean output of the most recent
# RECENT_WORKDAYS workdays with the mean of the BASELINE_WORKDAYS workdays
# before them. A drop of at least STAGE_DROP_PERCENT is flagged.
RECENT_WORKDAYS = 3
BASELINE_WORKDAYS = 7
STAGE_DROP_PERCENT = -20.0

# Discovery: a customer is flagged when it has at least this many unfinished
# orders and every one of them is overdue or quiet.
CUSTOMER_SLIPPING_MIN_ORDERS = 2

# Levels on the briefing page. An at-risk order is "act now" when it is at least this
# many calendar days late, or has gone quiet (QUIET_ORDER_DAYS without recorded
# activity); every other at-risk order is "watch". Stage drops and slipping customers
# have already passed their own thresholds above, so each of them is "act now".
# Each check is judged on its own.
ACT_NOW_LATE_DAYS = 7

# Outsourcing risk (outsourcing_risk.py). A workshop is flagged for quality when its defect rate is at
# least HIGH_DEFECT_RATE, for slow logistics when its pickup lead is at least SLOW_PICKUP_DAYS, and as
# busy when its current queue is at least BUSY_QUEUE_DAYS. A plan's risk level comes from its chance of
# missing the deadline (or, without a deadline, of any batch coming back defective): low below
# RISK_MEDIUM_FROM, high from RISK_HIGH_FROM. Provisional project choices, like the thresholds above.
HIGH_DEFECT_RATE = 0.08
SLOW_PICKUP_DAYS = 3
BUSY_QUEUE_DAYS = 4.0
RISK_MEDIUM_FROM = 0.05
RISK_HIGH_FROM = 0.20

# Discovery returns at most this many findings, ranked by severity.
MAX_FINDINGS = 5

# Feasibility scenario limits: the largest new batch a scenario may ask about, the longest
# in-house queue it may assume, and the most baseline workdays the production log can supply
# (the 90 days before the snapshot minus 13 Sundays).
MAX_SCENARIO_PIECES = 1_000_000
MAX_QUEUE_WORKDAYS = 365
MAX_BASELINE_WORKDAYS = 77


def parse_date(value):
    return date.fromisoformat(value)


def reference_date(as_of_date=None):
    return parse_date(as_of_date or today_iso())


def is_workday(day):
    return day.weekday() != REST_WEEKDAY


def previous_workdays(before, count):
    """List the count workdays strictly before the given date, newest first."""
    days = []
    cursor = before - timedelta(days=1)
    while len(days) < count:
        if is_workday(cursor):
            days.append(cursor)
        cursor -= timedelta(days=1)
    return days


def is_overdue(order, ref):
    return order["status"] == "IN_PROGRESS" and parse_date(order["due_date"]) < ref


def is_quiet(order, ref):
    if order["status"] != "IN_PROGRESS":
        return False
    return (ref - parse_date(order["last_activity_date"])).days >= QUIET_ORDER_DAYS


def is_due_soon(order, ref, due_within_days=DUE_SOON_DAYS):
    if order["status"] != "IN_PROGRESS":
        return False
    days_left = (parse_date(order["due_date"]) - ref).days
    return 0 <= days_left <= due_within_days


def risk_reasons(order, ref, due_within_days=DUE_SOON_DAYS):
    """Explain why an unfinished order needs attention; empty means no risk."""
    if order["status"] != "IN_PROGRESS":
        return []
    reasons = []
    if is_overdue(order, ref):
        days = (ref - parse_date(order["due_date"])).days
        reasons.append(f"overdue by {_calendar_days(days)}")
    elif is_due_soon(order, ref, due_within_days):
        days = (parse_date(order["due_date"]) - ref).days
        when = "due today" if days == 0 else f"due in {_calendar_days(days)}"
        reasons.append(f"{when}, still at stage {order['current_stage']}")
    if is_quiet(order, ref):
        days = (ref - parse_date(order["last_activity_date"])).days
        reasons.append(f"no recorded activity for {_calendar_days(days)}")
    return reasons


def _calendar_days(days):
    return f"{days} calendar day{'' if days == 1 else 's'}"
