"""Operational rules for the Track 1 co-pilot, as inspectable code.

Every judgement the system makes — what counts as overdue, quiet, at risk, or
an unusual drop in output — is defined here with its threshold, so the
definitions can be audited and tested instead of living inside a prompt.
Thresholds are provisional project choices, not validated business standards.
All rules evaluate against the dataset snapshot date; other dates are
scenarios, not facts.
"""

from datetime import date, timedelta

SNAPSHOT = "2026-04-01"

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

# Discovery returns at most this many findings, ranked by severity.
MAX_FINDINGS = 5


def parse_date(value):
    return date.fromisoformat(value)


def reference_date(as_of_date=SNAPSHOT):
    return parse_date(as_of_date)


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
        reasons.append(f"overdue by {days} calendar days")
    elif is_due_soon(order, ref, due_within_days):
        days = (parse_date(order["due_date"]) - ref).days
        reasons.append(f"due in {days} calendar days, still at stage {order['current_stage']}")
    if is_quiet(order, ref):
        days = (ref - parse_date(order["last_activity_date"])).days
        reasons.append(f"no recorded activity for {days} calendar days")
    return reasons
