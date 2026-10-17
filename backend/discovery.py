"""Discovery tool: find what nobody asked about.

Scans the snapshot for four kinds of finding — stage output drops, overdue
orders, quiet orders, and customers whose unfinished orders are all slipping —
then ranks them so a handful of items make the briefing page instead of forty.
Every rule and threshold lives in rules.py; every finding cites its source rows.
"""

from datetime import date

from data_loader import (ORDERS_SOURCE, PRODUCTION_SOURCE, STAGES, load_orders,
                         load_production, order_row_numbers,
                         production_row_numbers, source_ref)
from rules import (BASELINE_WORKDAYS, CUSTOMER_SLIPPING_MIN_ORDERS,
                   MAX_FINDINGS, RECENT_WORKDAYS, SNAPSHOT,
                   STAGE_DROP_PERCENT, is_overdue, is_quiet, previous_workdays, risk_reasons)


def _stage_output_drops(records, row_numbers, ref):
    """Flag stages whose recent workday average dropped versus its baseline."""
    findings = []
    data_gaps = []
    for stage in STAGES:
        recent_days = previous_workdays(ref, RECENT_WORKDAYS)
        baseline_days = previous_workdays(recent_days[-1], BASELINE_WORKDAYS)
        wanted = [(day.isoformat(), stage) for day in recent_days + baseline_days]
        values = {}
        missing = False
        for key in wanted:
            match = next((r for r in records
                          if r["date"] == key[0] and r["stage"] == stage), None)
            if match is None:
                missing = True
                break
            values[key] = int(match["pieces_completed"])
        if missing:
            data_gaps.append({"stage": stage, "reason": "Missing production records for the comparison window."})
            continue
        baseline_mean = sum(values[key] for key in wanted[RECENT_WORKDAYS:]) / BASELINE_WORKDAYS
        if baseline_mean == 0:
            data_gaps.append({"stage": stage, "reason": "Baseline mean is zero; percentage change is undefined."})
            continue
        recent_mean = sum(values[key] for key in wanted[:RECENT_WORKDAYS]) / RECENT_WORKDAYS
        change_percent = (recent_mean - baseline_mean) / baseline_mean * 100
        if change_percent <= STAGE_DROP_PERCENT:
            findings.append({
                "type": "stage_output_drop",
                "severity": round(-change_percent, 2),
                "severity_basis": "percentage-point drop of the recent "
                                  f"{RECENT_WORKDAYS}-workday mean vs the prior "
                                  f"{BASELINE_WORKDAYS}-workday mean",
                "summary": f"{stage} output fell {abs(change_percent):.1f}% "
                           f"(recent mean {recent_mean:.1f} vs baseline {baseline_mean:.1f} pieces/workday).",
                "details": {
                    "stage": stage,
                    "recent_workdays": RECENT_WORKDAYS,
                    "baseline_workdays": BASELINE_WORKDAYS,
                    "recent_mean": round(recent_mean, 2),
                    "baseline_mean": round(baseline_mean, 2),
                    "change_percent": round(change_percent, 2),
                },
                "evidence": {
                    "source": PRODUCTION_SOURCE,
                    "source_rows": [source_ref(PRODUCTION_SOURCE, row_numbers[key],
                                               f"{key[0]} {key[1]}")
                                    for key in wanted],
                },
            })
    return findings, data_gaps


def _order_findings(orders, order_rows, ref):
    """One finding per overdue or quiet unfinished order, plus slipping customers."""
    findings = []
    for order in orders:
        overdue_days = (ref - date.fromisoformat(order["due_date"])).days \
            if is_overdue(order, ref) else 0
        idle_days = (ref - date.fromisoformat(order["last_activity_date"])).days \
            if is_quiet(order, ref) else 0
        reasons = risk_reasons(order, ref)
        if not reasons:
            continue
        parts = reasons
        findings.append({
            "type": "order_at_risk",
            "severity": overdue_days * 2 + idle_days,
            "severity_basis": "2 x overdue calendar days + idle calendar days",
            "summary": f"{order['order_id']} ({order['customer']}, {order['pieces']} pcs, "
                       f"stage {order['current_stage']}): {'; '.join(parts)}.",
            "details": {
                    "order_id": order["order_id"],
                    "risk_reasons": reasons,
                "customer": order["customer"],
                "current_stage": order["current_stage"],
                "due_date": order["due_date"],
                "last_activity_date": order["last_activity_date"],
                "overdue_calendar_days": overdue_days,
                "idle_calendar_days": idle_days,
            },
            "evidence": {
                "source": ORDERS_SOURCE,
                "source_rows": [source_ref(ORDERS_SOURCE, order_rows[order["order_id"]],
                                           order["order_id"])],
            },
        })
    return findings


def _customer_findings(orders, order_rows, ref):
    """Flag customers whose unfinished orders are all overdue or quiet."""
    by_customer = {}
    for order in orders:
        if order["status"] == "IN_PROGRESS":
            by_customer.setdefault(order["customer"], []).append(order)
    findings = []
    for customer, customer_orders in by_customer.items():
        if len(customer_orders) < CUSTOMER_SLIPPING_MIN_ORDERS:
            continue
        if all(is_overdue(order, ref) or is_quiet(order, ref) for order in customer_orders):
            findings.append({
                "type": "customer_slipping",
                "severity": 10 * len(customer_orders),
                "severity_basis": f"10 x number of unfinished orders (all overdue or quiet)",
                "summary": f"All {len(customer_orders)} unfinished {customer} orders are "
                           "overdue or quiet.",
                "details": {
                    "customer": customer,
                    "order_ids": [order["order_id"] for order in customer_orders],
                },
                "evidence": {
                    "source": ORDERS_SOURCE,
                    "source_rows": [source_ref(ORDERS_SOURCE, order_rows[order["order_id"]],
                                               order["order_id"])
                                    for order in customer_orders],
                },
            })
    return findings


def discover_issues(as_of_date=SNAPSHOT, max_findings=MAX_FINDINGS):
    """Scan the snapshot and return the highest-severity findings with evidence."""
    try:
        ref = date.fromisoformat(as_of_date)
    except (TypeError, ValueError):
        return {"status": "error", "message": "Use a valid date in YYYY-MM-DD format."}
    if type(max_findings) is not int or max_findings <= 0:
        return {"status": "error", "message": "max_findings must be a positive integer."}

    orders = load_orders()
    records = load_production()
    stage_findings, data_gaps = _stage_output_drops(records, production_row_numbers(), ref)
    order_rows = order_row_numbers()
    groups = {
        "order_at_risk": _order_findings(orders, order_rows, ref),
        "stage_output_drop": stage_findings,
        "customer_slipping": _customer_findings(orders, order_rows, ref),
    }
    for group in groups.values():
        group.sort(key=lambda finding: finding["severity"], reverse=True)
    # 各类别轮流取一项，避免不同单位的分数直接比较。
    findings = []
    for index in range(max((len(group) for group in groups.values()), default=0)):
        for group in groups.values():
            if index < len(group):
                findings.append(group[index])
    selected = findings[:max_findings]

    return {
        "status": "ok",
        "as_of_date": ref.isoformat(),
        "snapshot_date": SNAPSHOT,
        "total_findings": len(findings),
        "count": min(len(findings), max_findings),
        "findings": selected,
        "groups": {kind: [f for f in selected if f["type"] == kind] for kind in groups},
        "data_gaps": data_gaps,
        "coverage_complete": not data_gaps,
        "selection_policy": "Round-robin across types, ranked only within each type; no universal severity ranking.",
        "rules": "Thresholds and severity formulas are defined in rules.py; "
                 "severity units differ per finding type (see severity_basis).",
        "warnings": [
            "Findings are signals to investigate, not diagnoses; the data cannot say why something dropped."
        ] + ([] if as_of_date == SNAPSHOT else [
            f"Uses order statuses from the {SNAPSHOT} snapshot; other dates are scenarios, not historical or future facts."
        ]),
    }
