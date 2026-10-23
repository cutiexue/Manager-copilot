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

from data_loader import PRODUCTION_SOURCE, STAGES
from discovery import discover_issues
from rules import MAX_FINDINGS, SNAPSHOT, is_workday
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
