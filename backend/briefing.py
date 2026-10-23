"""Assemble the morning briefing from the tool layer.

Every number in the briefing comes from the same tools the chat agent uses —
nothing is recomputed here, and the prose rendering is deterministic so the
scheduler can generate the briefing without an LLM call. The agent may narrate
the structured result, but it must not invent numbers beyond it.
"""

import csv
import subprocess
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from data_loader import PRODUCTION_SOURCE, STAGES, source_ref
from discovery import discover_issues
from rules import (BASELINE_WORKDAYS, CUSTOMER_SLIPPING_MIN_ORDERS, DUE_SOON_DAYS, MAX_FINDINGS,
                   QUIET_ORDER_DAYS, RECENT_WORKDAYS, REVIEW_LATE_DAYS, SNAPSHOT, STAGE_DROP_PERCENT,
                   is_due_soon, is_overdue, is_workday)
from tools import compare_stage_output, get_orders_at_risk, get_stage_output

# Each finding type maps to one fixed decision prompt; these are prompts for
# the manager, not conclusions drawn by the system.
_DECISION_PROMPTS = {
    "order_at_risk": "Check the latest progress and whether follow-up is needed.",
    "customer_slipping": "Review the affected orders before deciding whether customer contact is needed.",
    "stage_output_drop": "Check the production records and investigate the drop if confirmed.",
}


def _yesterday_section(yesterday):
    """Per-stage output for yesterday with its baseline comparison."""
    if not is_workday(yesterday):
        return {
            "date": yesterday.isoformat(),
            "is_workday": False,
            "message": "Yesterday was a scheduled rest day; actual output was not checked.",
            "stages": [],
        }
    stages = []
    for stage in STAGES:
        output = get_stage_output(stage, yesterday.isoformat())
        comparison = compare_stage_output(stage, yesterday.isoformat())
        entry = {"stage": stage}
        if output["status"] == "ok":
            entry["pieces_completed"] = output["data"]["pieces_completed"]
            entry["source_rows"] = output["source_rows"]
        else:
            entry["output_status"] = output["status"]
            entry["message"] = output.get("message")
        if comparison["status"] == "ok":
            entry["baseline_workdays"] = comparison["data"]["baseline_workdays"]
            entry["baseline_average"] = comparison["data"]["baseline_average"]
            entry["change_percent"] = comparison["data"]["change_percent"]
            entry["baseline_records"] = comparison["baseline_records"]
        else:
            entry["comparison_status"] = comparison["status"]
        stages.append(entry)
    return {"date": yesterday.isoformat(), "is_workday": True, "stages": stages}


def _join(parts):
    """'a', 'a and b', 'a, b and c'."""
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def _summary(ref, yesterday, risk_orders, risk_rows, findings, data_gaps):
    """A short paragraph for the top of the briefing, one sourced sentence per check.

    Every sentence is built from the same tool outputs as the rest of the briefing and
    carries its own source rows, so the summary adds no numbers and needs no LLM call.
    """
    points = []

    def add(kind, text, rows=None, **subject):
        evidence = {"source": rows[0]["source"], "source_rows": rows} if rows else None
        points.append({"kind": kind, "text": text, **subject, "evidence": evidence})

    # 1. 需要关注的未完成订单，按原因分开计数（与 get_orders_at_risk 同一套规则，互不重叠）。
    overdue = [o for o in risk_orders if is_overdue(o, ref)]
    due_soon = [o for o in risk_orders if not is_overdue(o, ref) and is_due_soon(o, ref)]
    quiet_only = [o for o in risk_orders if not is_overdue(o, ref) and not is_due_soon(o, ref)]
    if risk_orders:
        parts = []
        if overdue:
            parts.append(f"{len(overdue)} {'is' if len(overdue) == 1 else 'are'} overdue")
        if due_soon:
            parts.append(f"{len(due_soon)} {'is' if len(due_soon) == 1 else 'are'} due within {DUE_SOON_DAYS} days")
        if quiet_only:
            parts.append(f"{len(quiet_only)} {'has' if len(quiet_only) == 1 else 'have'} had no recorded "
                         f"activity for {QUIET_ORDER_DAYS} days or more")
        count = len(risk_orders)
        add("orders_at_risk", f"{count} unfinished {'order needs' if count == 1 else 'orders need'} attention: "
                              f"{_join(parts)}.", risk_rows)
    else:
        add("orders_at_risk", "No unfinished order is overdue, due soon or quiet.")

    # 2. The most overdue order: earliest due date among overdue orders.
    if overdue:
        worst = min(overdue, key=lambda o: (o["due_date"], o["order_id"]))
        days = (ref - date.fromisoformat(worst["due_date"])).days
        add("most_overdue", f"The most overdue is {worst['order_id']} for {worst['customer']}, "
                            f"{days} days past its due date.",
            [row for row in risk_rows if row["key"] == worst["order_id"]], order_id=worst["order_id"])

    # 3. Stage output drops from discovery (recent workdays vs the workdays before).
    drops = [f for f in findings if f["type"] == "stage_output_drop"]
    for finding in drops:
        d = finding["details"]
        add("stage_output_drop", f"{d['stage']} output fell {abs(d['change_percent']):.1f}% over the last "
                                 f"{d['recent_workdays']} workdays compared with the {d['baseline_workdays']} before.",
            finding["evidence"]["source_rows"], stage=d["stage"])
    stage_gaps = [gap for gap in data_gaps if gap.get("section") != "yesterday"]
    if not drops and not stage_gaps:
        add("no_stage_drop", f"No stage's output fell {abs(STAGE_DROP_PERCENT):.0f}% or more over the last "
                             f"{RECENT_WORKDAYS} workdays.")

    # 4. Customers whose unfinished orders are all overdue or quiet.
    for finding in (f for f in findings if f["type"] == "customer_slipping"):
        d = finding["details"]
        count = len(d["order_ids"])
        add("customer_slipping", f"{'Both' if count == 2 else f'All {count}'} unfinished {d['customer']} orders "
                                 "are overdue or quiet.", finding["evidence"]["source_rows"], customer=d["customer"])

    # 5. Yesterday's output against each stage's own recent average.
    compared = [s for s in yesterday["stages"] if s.get("change_percent") is not None]
    if not yesterday["is_workday"]:
        add("yesterday", f"Yesterday ({yesterday['date']}) was a scheduled rest day.")
    elif compared:
        lowest = min(compared, key=lambda s: s["change_percent"])
        rows = [row for s in compared for row in s.get("source_rows", [])] + [
            source_ref(PRODUCTION_SOURCE, r["source_row"], f"{r['date']} {r['stage']}")
            for s in compared for r in s.get("baseline_records", [])]
        if lowest["change_percent"] < 0:
            others = [abs(s["change_percent"]) for s in compared if s is not lowest]
            text = (f"Yesterday ({yesterday['date']}) {lowest['stage']} completed {lowest['pieces_completed']} pieces, "
                    f"{abs(lowest['change_percent']):.1f}% below its {lowest['baseline_workdays']}-workday average")
            text += f"; the other stages were within {max(others):.1f}% of theirs." if others else "."
        else:
            text = f"Yesterday ({yesterday['date']}) every stage was at or above its {lowest['baseline_workdays']}-workday average."
        add("yesterday", text, rows)

    if data_gaps:
        add("data_gaps", f"{len(data_gaps)} {'check' if len(data_gaps) == 1 else 'checks'} could not be "
                         "completed because records are missing.")

    return {"text": " ".join(point["text"] for point in points), "points": points}


def _plural(count, noun):
    return f"{count} {noun}{'' if count == 1 else 's'}"


def _check_item(finding, ref):
    """One compact row for a finding: a name, its context, a short tag saying why it was found,
    and whether it is flagged for review under the rule in rules.py."""
    d = finding["details"]
    kind = finding["type"]
    if kind == "order_at_risk":
        parts = []
        if d["overdue_calendar_days"]:
            parts.append(f"{_plural(d['overdue_calendar_days'], 'day')} late")
        else:
            left = (date.fromisoformat(d["due_date"]) - ref).days
            if 0 <= left <= DUE_SOON_DAYS:
                parts.append("due today" if left == 0 else f"due in {_plural(left, 'day')}")
        if d["idle_calendar_days"]:
            parts.append(f"{_plural(d['idle_calendar_days'], 'day')} idle")
        name, context, tag = d["order_id"], f"{d['customer']} · {d['current_stage']}", " · ".join(parts)
        flagged = d["overdue_calendar_days"] >= REVIEW_LATE_DAYS or d["idle_calendar_days"] >= QUIET_ORDER_DAYS
    elif kind == "stage_output_drop":
        name = d["stage"]
        context = f"last {d['recent_workdays']} workdays vs previous {d['baseline_workdays']}"
        tag = f"{d['change_percent']:.1f}%"
        flagged = True
    else:
        name, context, tag = d["customer"], _plural(len(d["order_ids"]), "unfinished order"), "all overdue or quiet"
        flagged = True
    return {"key": name, "name": name, "context": context, "tag": tag, "flagged": flagged,
            "note": _DECISION_PROMPTS[kind], "finding": finding}


def _checks(ref, findings):
    """Every finding grouped by the check that produced it, with the ones that need review flagged.

    Each check is judged on its own (REVIEW_LATE_DAYS in rules.py), so how many items of one
    check are flagged never depends on the others. Listing all findings, not only the flagged
    ones, is what makes the flags meaningful.
    """
    basis = {f["type"]: f["severity_basis"] for f in reversed(findings)}
    meta = [
        ("order_at_risk", "Orders at risk",
         f"Unfinished orders that are overdue, due within {DUE_SOON_DAYS} days or without recorded "
         f"activity for {QUIET_ORDER_DAYS}+ days.",
         f"Flagged when {REVIEW_LATE_DAYS}+ days late or {QUIET_ORDER_DAYS}+ days without recorded activity."),
        ("stage_output_drop", "Production",
         f"Stages whose mean output over the last {RECENT_WORKDAYS} workdays is at least "
         f"{abs(STAGE_DROP_PERCENT):.0f}% below the {BASELINE_WORKDAYS} workdays before.",
         "Every stage found by this check is flagged."),
        ("customer_slipping", "Customers",
         f"Customers with at least {CUSTOMER_SLIPPING_MIN_ORDERS} unfinished orders, all overdue or quiet.",
         "Every customer found by this check is flagged."),
    ]
    checks = []
    for kind, title, how_picked, flag_rule in meta:
        items = [_check_item(f, ref) for f in findings if f["type"] == kind]
        # 同类结果已按严重度排序；入选审查的项提到最前，其余保持原有顺序。
        items.sort(key=lambda item: not item["flagged"])
        checks.append({"type": kind, "title": title, "total": len(items),
                       "flagged": sum(item["flagged"] for item in items),
                       "how_picked": how_picked, "flag_rule": flag_rule, "ranked_by": basis.get(kind),
                       "items": items})
    return checks


def get_morning_briefing(as_of_date=SNAPSHOT, max_findings=MAX_FINDINGS):
    """Structured morning briefing: yesterday, what is at risk, what needs a decision."""
    try:
        ref = date.fromisoformat(as_of_date)
    except (TypeError, ValueError):
        return {"status": "error", "message": "Use a valid date in YYYY-MM-DD format."}
    if type(max_findings) is not int or max_findings <= 0:
        return {"status": "error", "message": "max_findings must be a positive integer."}

    yesterday = _yesterday_section(ref - timedelta(days=1))
    risk = get_orders_at_risk(as_of_date)
    findings_result = discover_issues(as_of_date, max_findings)
    findings = findings_result["findings"]
    # The summary and the review lists cover every finding, not only the ones selected for decisions.
    all_findings = discover_issues(as_of_date, max(findings_result["total_findings"], 1))["findings"]
    checks = _checks(ref, all_findings)
    data_gaps = list(findings_result["data_gaps"])
    for entry in yesterday["stages"]:
        for field in ("output_status", "comparison_status"):
            if field in entry:
                data_gaps.append({"stage": entry["stage"], "section": "yesterday",
                                  "reason": entry[field]})
    customer_order_ids = {
        order_id for finding in findings if finding["type"] == "customer_slipping"
        for order_id in finding["details"]["order_ids"]
    }
    decisions = [
        {
            "finding_type": finding["type"],
            "about": finding["summary"],
            "suggested_decision": _DECISION_PROMPTS[finding["type"]],
            "evidence": finding["evidence"],
        }
        for finding in findings
        if not (finding["type"] == "order_at_risk"
                and finding["details"]["order_id"] in customer_order_ids)
    ]

    return {
        "status": "ok",
        "as_of_date": ref.isoformat(),
        "snapshot_date": SNAPSHOT,
        "yesterday": yesterday,
        "at_risk": {
            "count": risk["count"],
            "orders": [
                {"order_id": order["order_id"], "customer": order["customer"],
                 "current_stage": order["current_stage"],
                 "risk_reasons": order["risk_reasons"]}
                for order in risk["data"]
            ],
            "source_rows": risk["source_rows"],
        },
        "summary": _summary(ref, yesterday, risk["data"], risk["source_rows"], all_findings, data_gaps),
        "checks": checks,
        "review_count": sum(check["flagged"] for check in checks),
        "total_findings": findings_result["total_findings"],
        "findings": findings,
        "decisions": decisions,
        "coverage_complete": not data_gaps,
        "data_gaps": data_gaps,
        "comparison_windows": {
            "yesterday": "One day vs the previous seven workdays.",
            "discovery": "Recent three workdays vs the preceding seven workdays.",
        },
        "warnings": [
            "This briefing is assembled deterministically from tool outputs; "
            "findings are signals to investigate, not diagnoses."
        ] + (["Some checks could not be completed; see data_gaps."] if data_gaps else []) + ([] if as_of_date == SNAPSHOT else [
            f"Uses order statuses from the {SNAPSHOT} snapshot; other dates are scenarios, not historical or future facts."
        ]),
    }


def render_briefing_text(briefing):
    """Render the structured briefing as concise prose, first three lines first."""
    if briefing.get("status") != "ok":
        return f"Briefing unavailable: {briefing.get('message', 'unknown error')}"

    lines = [f"Morning briefing — {briefing['as_of_date']} (snapshot {briefing['snapshot_date']})"]
    if "summary" in briefing:
        lines += [briefing["summary"]["text"], ""]

    yesterday = briefing["yesterday"]
    if yesterday["is_workday"]:
        parts = []
        for entry in yesterday["stages"]:
            if "pieces_completed" in entry:
                change = entry.get("change_percent")
                suffix = f" ({change:+.1f}%)" if change is not None else ""
                parts.append(f"{entry['stage']} {entry['pieces_completed']}{suffix}")
            else:
                parts.append(f"{entry['stage']} {entry.get('output_status', 'unknown')}")
        lines.append(f"Yesterday ({yesterday['date']}): " + "; ".join(parts))
    else:
        lines.append(f"Yesterday ({yesterday['date']}): scheduled rest day, no output expected.")

    at_risk = briefing["at_risk"]
    lines.append(f"Orders at risk: {at_risk['count']} | "
                 f"Findings: {briefing['total_findings']} (grouped by type)")

    if briefing["decisions"]:
        lines.append("")
        lines.append(f"Suggested follow-up checks ({len(briefing['decisions'])}):")
        for decision in briefing["decisions"]:
            lines.append(f"- {decision['about']} {decision['suggested_decision']}")

    if yesterday["is_workday"]:
        lines.append("")
        lines.append("Yesterday vs baseline:")
        for entry in yesterday["stages"]:
            if "change_percent" in entry and entry["change_percent"] is not None:
                lines.append(
                    f"- {entry['stage']}: {entry['pieces_completed']} pcs vs "
                    f"{entry['baseline_average']:.1f} avg over "
                    f"{entry['baseline_workdays']} workdays "
                    f"({entry['change_percent']:+.1f}%)")

    lines.append("")
    lines.append("Every figure traces to the source rows in the structured briefing.")
    lines.append("Windows: yesterday vs prior 7 workdays; discovery uses recent 3 vs preceding 7 workdays.")
    lines.extend(f"Warning: {warning}" for warning in briefing["warnings"])
    lines.extend(f"Data gap: {gap['stage']}: {gap['reason']}" for gap in briefing["data_gaps"])
    return "\n".join(lines)


BACKEND_DIR = Path(__file__).resolve().parent


def _collect_refs(node, refs):
    """Gather every (source, row) citation in a tool result."""
    if isinstance(node, dict):
        if "source" in node and "row" in node:
            refs.add((node["source"], node["row"]))
        elif "source_row" in node:
            # baseline_records 只带行号，来源固定是 production_log.csv。
            refs.add((PRODUCTION_SOURCE, node["source_row"]))
        for value in node.values():
            _collect_refs(value, refs)
    elif isinstance(node, list):
        for value in node:
            _collect_refs(value, refs)


@lru_cache(maxsize=1)
def _backend_commit():
    try:
        result = subprocess.run(["git", "-C", str(BACKEND_DIR), "rev-parse", "--short", "HEAD"],
                                capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def get_briefing_payload(as_of_date=SNAPSHOT):
    """Briefing plus the raw CSV rows it cites, in the shape of the frontend fixture."""
    briefing = get_morning_briefing(as_of_date)
    if briefing.get("status") != "ok":
        raise ValueError(briefing.get("message", "Briefing could not be generated."))
    refs = set()
    _collect_refs(briefing, refs)
    tables = {}
    rows = {}
    for source, row in sorted(refs):
        if source not in tables:
            with (BACKEND_DIR / source).open(encoding="utf-8-sig", newline="") as handle:
                tables[source] = list(csv.reader(handle))
        header, values = tables[source][0], tables[source][row - 1]  # row 是文件行号，表头为第 1 行
        rows[f"{source}#{row}"] = dict(zip(header, values))
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": "GET /briefings/latest",
        "backend_commit": _backend_commit(),
        "briefing": briefing,
        "source_rows": rows,
        "briefing_text": render_briefing_text(briefing),
    }
