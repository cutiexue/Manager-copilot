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
from rules import (ACT_NOW_LATE_DAYS, BASELINE_WORKDAYS, CUSTOMER_SLIPPING_MIN_ORDERS, DUE_SOON_DAYS,
                   MAX_FINDINGS, QUIET_ORDER_DAYS, RECENT_WORKDAYS, SNAPSHOT, STAGE_DROP_PERCENT,
                   is_due_soon, is_overdue, is_workday, previous_workdays)
from tools import compare_stage_output, get_orders_at_risk, get_stage_output

# Each finding type maps to one fixed decision prompt; these are prompts for
# the manager, not conclusions drawn by the system.
_DECISION_PROMPTS = {
    "order_at_risk": "Check the latest progress and whether follow-up is needed.",
    "customer_slipping": "Review the affected orders before deciding whether customer contact is needed.",
    "stage_output_drop": "Check the production records and investigate the drop if confirmed.",
}


def _yesterday_section(day, ref):
    """Per-stage output for one day with its baseline comparison.

    The briefing passes the last workday before its date, so a Monday briefing reports Saturday
    rather than the Sunday rest day; `label` says whether that is literally yesterday."""
    label = "Yesterday" if day == ref - timedelta(days=1) else "Last workday"
    if not is_workday(day):
        return {
            "date": day.isoformat(),
            "label": label,
            "is_workday": False,
            "message": f"{day.isoformat()} was a scheduled rest day; actual output was not checked.",
            "stages": [],
        }
    stages = []
    for stage in STAGES:
        output = get_stage_output(stage, day.isoformat())
        comparison = compare_stage_output(stage, day.isoformat())
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
    return {"date": day.isoformat(), "label": label, "is_workday": True, "stages": stages}


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

    # 5. The last workday's output against each stage's own recent average.
    compared = [s for s in yesterday["stages"] if s.get("change_percent") is not None]
    when = f"{yesterday.get('label', 'Yesterday')} ({yesterday['date']})"
    if not yesterday["is_workday"]:
        add("yesterday", f"{when} was a scheduled rest day.")
    elif compared:
        lowest = min(compared, key=lambda s: s["change_percent"])
        rows = [row for s in compared for row in s.get("source_rows", [])] + [
            source_ref(PRODUCTION_SOURCE, r["source_row"], f"{r['date']} {r['stage']}")
            for s in compared for r in s.get("baseline_records", [])]
        if lowest["change_percent"] < 0:
            others = [abs(s["change_percent"]) for s in compared if s is not lowest]
            text = (f"{when} {lowest['stage']} completed {lowest['pieces_completed']} pieces, "
                    f"{abs(lowest['change_percent']):.1f}% below its {lowest['baseline_workdays']}-workday average")
            text += f"; the other stages were within {max(others):.1f}% of theirs." if others else "."
        else:
            text = f"{when} every stage was at or above its {lowest['baseline_workdays']}-workday average."
        add("yesterday", text, rows)

    if data_gaps:
        add("data_gaps", f"{len(data_gaps)} {'check' if len(data_gaps) == 1 else 'checks'} could not be "
                         "completed because records are missing.")

    return {"text": " ".join(point["text"] for point in points), "points": points}


def _plural(count, noun):
    return f"{count} {noun}{'' if count == 1 else 's'}"


def _rows_of(*evidence):
    """Source rows from several evidence blocks, each row once, in order."""
    seen, rows = set(), []
    for block in evidence:
        for row in (block or {}).get("source_rows", []):
            if (row["source"], row["row"]) not in seen:
                seen.add((row["source"], row["row"]))
                rows.append(row)
    return rows


def _narrative(ref, yesterday, risk_orders, risk_rows, checks):
    """The briefing in three sentences, in the order the track asks for: what happened yesterday,
    what is at risk, what needs action today. Built from the same tool outputs and level rules as
    the rest of the page; every sentence keeps the source rows behind it."""
    sentences = []

    def add(topic, text, rows):
        evidence = {"source": rows[0]["source"], "source_rows": rows} if rows else None
        sentences.append({"topic": topic, "text": text, "evidence": evidence})

    # 1. What happened on the last workday, against each stage's own recent average.
    day = date.fromisoformat(yesterday["date"])
    when = "Yesterday" if yesterday.get("label", "Yesterday") == "Yesterday" else \
        f"On {day:%a} {day.day} {day:%b}, the last workday,"
    compared = [s for s in yesterday["stages"] if s.get("change_percent") is not None]
    if not yesterday["is_workday"]:
        add("yesterday", f"{when} was a scheduled rest day.", [])
    elif not compared:
        add("yesterday", f"{when}'s output could not be compared: records are missing.", [])
    else:
        rows = [row for s in compared for row in s.get("source_rows", [])] + [
            source_ref(PRODUCTION_SOURCE, r["source_row"], f"{r['date']} {r['stage']}")
            for s in compared for r in s.get("baseline_records", [])]
        lowest = min(compared, key=lambda s: s["change_percent"])
        window = f"{lowest['baseline_workdays']}-workday average"
        if lowest["change_percent"] < 0:
            text = (f"{when} {lowest['stage'].lower()} made {lowest['pieces_completed']:,} pieces, "
                    f"{abs(lowest['change_percent']):.1f}% below its {window}")
            others = [s for s in compared if s is not lowest]
            nxt = min(others, key=lambda s: s["change_percent"]) if others else None
            if nxt is None:
                text += "."
            elif nxt["change_percent"] < 0:
                text += f"; {nxt['stage'].lower()} was next lowest, {abs(nxt['change_percent']):.1f}% below."
            else:
                text += "; the other stages were at or above theirs."
        else:
            text = f"{when} every stage was at or above its {window}."
        add("yesterday", text[0].upper() + text[1:], rows)

    # 2. What is at risk: the same three reasons as get_orders_at_risk, counted without overlap.
    overdue = [o for o in risk_orders if is_overdue(o, ref)]
    due_soon = [o for o in risk_orders if not is_overdue(o, ref) and is_due_soon(o, ref)]
    idle_only = [o for o in risk_orders if not is_overdue(o, ref) and not is_due_soon(o, ref)]
    if risk_orders:
        parts = [f"{len(overdue)} overdue"] if overdue else []
        parts += [f"{len(due_soon)} due within {_plural(DUE_SOON_DAYS, 'day')}"] if due_soon else []
        parts += [f"{len(idle_only)} idle {QUIET_ORDER_DAYS}+ days"] if idle_only else []
        count = len(risk_orders)
        text = f"{count} {'order is' if count == 1 else 'orders are'} at risk ({', '.join(parts)})"
        if overdue:
            worst = min(overdue, key=lambda o: (o["due_date"], o["order_id"]))
            days = (ref - date.fromisoformat(worst["due_date"])).days
            text += (f"; {worst['order_id']} for {worst['customer']} is the furthest behind at "
                     f"{_plural(days, 'day')} late.")
        else:
            text += "."
        add("at_risk", text, risk_rows)
    else:
        add("at_risk", f"No order is overdue, due within {_plural(DUE_SOON_DAYS, 'day')} or idle "
                       f"{QUIET_ORDER_DAYS}+ days.", [])

    # 3. What needs action today: the Act now items of every check, named by check.
    by_type = {check["type"]: [i for i in check["items"] if i["level"] == "act"] for check in checks}
    parts = []
    orders = by_type.get("order_at_risk", [])
    if orders:
        rule = _level_rules()["order_at_risk"]["act"]
        parts.append(f"{_plural(len(orders), 'order')} {rule[0].lower()}{rule[1:]}")
    for item in by_type.get("stage_output_drop", []):
        d = item["finding"]["details"]
        parts.append(f"the {abs(d['change_percent']):.1f}% drop in {d['stage'].lower()} output over the "
                     f"last {d['recent_workdays']} workdays")
    for item in by_type.get("customer_slipping", []):
        n = len(item["finding"]["details"]["order_ids"])
        parts.append(f"customer {item['name']} ({'both' if n == 2 else f'all {n}'} open orders slipping)")
    act = [i for items in by_type.values() for i in items]
    if act:
        add("today", f"{len(act)} {'item needs' if len(act) == 1 else 'items need'} action today: {_join(parts)}.",
            _rows_of(*(i["finding"]["evidence"] for i in act)))
    else:
        watch = _level_count(checks, "watch")
        add("today", "Nothing needs action today" + (f"; {_plural(watch, 'item')} to watch." if watch else "."), [])

    return {"text": " ".join(s["text"] for s in sentences), "sentences": sentences}


_LEVEL_LABELS = {"act": "Act now", "watch": "Watch"}


def _check_item(finding, ref):
    """One compact row for a finding: a name, its context, a short tag saying why it was found,
    and its level on the briefing page ("act" or "watch") under the rules in rules.py."""
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
        act = d["overdue_calendar_days"] >= ACT_NOW_LATE_DAYS or d["idle_calendar_days"] >= QUIET_ORDER_DAYS
    elif kind == "stage_output_drop":
        name = d["stage"]
        context = f"{d['recent_mean']:.0f} vs {d['baseline_mean']:.0f} pcs/workday"
        tag = f"{d['change_percent']:.1f}%".replace("-", "−")
        act = True
    else:
        name, context, tag = d["customer"], ", ".join(d["order_ids"]), _plural(len(d["order_ids"]), "order")
        act = True
    return {"key": name, "name": name, "context": context, "tag": tag, "level": "act" if act else "watch",
            "note": _DECISION_PROMPTS[kind], "finding": finding}


def _level_rules():
    """What puts an item of each check at each level, in words short enough to sit above the items."""
    if ACT_NOW_LATE_DAYS == QUIET_ORDER_DAYS:
        late_or_idle = f"Late or idle {ACT_NOW_LATE_DAYS}+ days"
    else:
        late_or_idle = f"Late {ACT_NOW_LATE_DAYS}+ days or idle {QUIET_ORDER_DAYS}+ days"
    return {
        "order_at_risk": {
            "act": late_or_idle,
            "watch": f"Late under {_plural(ACT_NOW_LATE_DAYS, 'day')} or due within {_plural(DUE_SOON_DAYS, 'day')}",
        },
        "stage_output_drop": {
            "act": f"Output down {abs(STAGE_DROP_PERCENT):.0f}%+ "
                   f"(last {RECENT_WORKDAYS} workdays vs previous {BASELINE_WORKDAYS})",
        },
        "customer_slipping": {
            "act": f"{CUSTOMER_SLIPPING_MIN_ORDERS}+ unfinished orders, all late or idle",
        },
    }


def _row_order(item, ref):
    """Act now before watch; within a level the highest score first, then the earliest due date."""
    details = item["finding"]["details"]
    days_left = (date.fromisoformat(details["due_date"]) - ref).days if "due_date" in details else 0
    return (item["level"] != "act", -item["finding"]["severity"], days_left)


def _checks(ref, findings):
    """Every finding grouped by the check that produced it, each at a level: act now or watch.

    Each check is judged on its own (ACT_NOW_LATE_DAYS in rules.py), so an item's level never
    depends on the other checks. Every item carries a level, and each level carries the rule
    that put items there, so the page can show the rule beside the items it explains.
    """
    basis = {f["type"]: f["severity_basis"] for f in reversed(findings)}
    rules = _level_rules()
    meta = [
        ("order_at_risk", "Orders at risk",
         f"Unfinished orders that are overdue, due within {DUE_SOON_DAYS} days or without recorded "
         f"activity for {QUIET_ORDER_DAYS}+ days."),
        ("stage_output_drop", "Production",
         f"Stages whose mean output over the last {RECENT_WORKDAYS} workdays is at least "
         f"{abs(STAGE_DROP_PERCENT):.0f}% below the {BASELINE_WORKDAYS} workdays before."),
        ("customer_slipping", "Customers",
         f"Customers with at least {CUSTOMER_SLIPPING_MIN_ORDERS} unfinished orders, all overdue or quiet."),
    ]
    checks = []
    for kind, title, how_picked in meta:
        items = sorted((_check_item(f, ref) for f in findings if f["type"] == kind),
                       key=lambda item: _row_order(item, ref))
        levels = [{"level": level, "label": _LEVEL_LABELS[level], "rule": rule,
                   "count": sum(item["level"] == level for item in items)}
                  for level, rule in rules[kind].items()]
        checks.append({"type": kind, "title": title, "total": len(items), "how_picked": how_picked,
                       "ranked_by": basis.get(kind), "levels": levels, "items": items})
    return checks


def _level_count(checks, level):
    return sum(entry["count"] for check in checks for entry in check["levels"] if entry["level"] == level)


def get_morning_briefing(as_of_date=SNAPSHOT, max_findings=MAX_FINDINGS, narrative_rows=False):
    """Structured morning briefing: yesterday, what is at risk, what needs a decision.

    The agent gets the narrative as text only: its source rows are already in the sections above
    it, so repeating them would only lengthen the tool result. The page (narrative_rows=True)
    keeps them so each sentence opens its rows."""
    try:
        ref = date.fromisoformat(as_of_date)
    except (TypeError, ValueError):
        return {"status": "error", "message": "Use a valid date in YYYY-MM-DD format."}
    if type(max_findings) is not int or max_findings <= 0:
        return {"status": "error", "message": "max_findings must be a positive integer."}

    yesterday = _yesterday_section(previous_workdays(ref, 1)[0], ref)
    risk = get_orders_at_risk(as_of_date)
    findings_result = discover_issues(as_of_date, max_findings)
    findings = findings_result["findings"]
    # The summary and the review lists cover every finding, not only the ones selected for decisions.
    all_findings = discover_issues(as_of_date, max(findings_result["total_findings"], 1))["findings"]
    checks = _checks(ref, all_findings)
    narrative = _narrative(ref, yesterday, risk["data"], risk["source_rows"], checks)
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
        "narrative": narrative if narrative_rows else {
            "text": narrative["text"],
            "sentences": [{"topic": n["topic"], "text": n["text"]} for n in narrative["sentences"]]},
        "checks": checks,
        "act_count": _level_count(checks, "act"),
        "watch_count": _level_count(checks, "watch"),
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
        ] + (["Some checks could not be completed; see data_gaps."] if data_gaps else []) + ([] if ref.isoformat() == SNAPSHOT else [
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
    label = yesterday.get("label", "Yesterday")
    if yesterday["is_workday"]:
        parts = []
        for entry in yesterday["stages"]:
            if "pieces_completed" in entry:
                change = entry.get("change_percent")
                suffix = f" ({change:+.1f}%)" if change is not None else ""
                parts.append(f"{entry['stage']} {entry['pieces_completed']}{suffix}")
            else:
                parts.append(f"{entry['stage']} {entry.get('output_status', 'unknown')}")
        lines.append(f"{label} ({yesterday['date']}): " + "; ".join(parts))
    else:
        lines.append(f"{label} ({yesterday['date']}): scheduled rest day, no output expected.")

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
        lines.append(f"{label} vs baseline:")
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
    briefing = get_morning_briefing(as_of_date, narrative_rows=True)
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
