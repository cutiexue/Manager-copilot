"""Turn the saved scenario records into readable transcripts (Markdown), one file per scenario plus an index.

Usage: python3 render_transcripts.py <report_questions dir>
Nothing is summarised away: every chat turn shows the full answer, every tool call with its arguments and
status, the answer check and proposals; every click, scheduler run and state read is listed.
"""

import json
import sys
from pathlib import Path


def short(value, limit=600):
    text = json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[:limit] + f"... ({len(text)} chars, full record in the JSON file)"


def state_lines(state):
    lines = []
    proposals = state.get("/actions", [])
    lines.append(f"- proposals: {[(p['kind'], (p.get('payload') or {}).get('order_id'), p['status']) for p in proposals]}")
    lines.append(f"- notes: {[(n.get('order_id'), n.get('text')) for n in state.get('/notes', [])]}")
    lines.append(f"- reminders: {[(r.get('remind_at'), r.get('status'), r.get('text')) for r in state.get('/reminders', [])]}")
    lines.append(f"- drafts: {[(d.get('order_id'), (d.get('text') or '')[:80]) for d in state.get('/drafts', [])]}")
    lines.append(f"- watches: {[(w.get('order_id'), w.get('condition'), w.get('deadline'), w.get('status')) for w in state.get('/watches', [])]}")
    lines.append(f"- alerts: {[(a.get('kind'), a.get('title')) for a in state.get('/alerts', [])]}")
    lines.append(f"- audit events: {[a.get('event') for a in state.get('/audit', [])]}")
    return lines


def render(record):
    out = [f"# {record['scenario']} (grades {', '.join(record['questions'])})", ""]
    if record.get("adaptation"):
        out += [f"Setup differs from the report: {record['adaptation']}", ""]
    run = record.get("run", {})
    out += [f"Model {run.get('provider')}/{run.get('model')}, prompt version {run.get('prompt_version')}, "
            f"code {str(run.get('git_head'))[:7]} plus the uncommitted changes recorded in code_version/. "
            f"Started {record['started_at']}, finished {record.get('finished_at')}.", ""]
    for number, step in enumerate(record["steps"], 1):
        kind = step["step"]
        if kind == "chat":
            reply = step.get("reply", {})
            label = f" — graded as {step['qid']}" if step.get("qid") else " — setup turn"
            out += [f"## Step {number}: manager message{label}", "", "> " + step["message"], "",
                    f"HTTP {step.get('http_status')}, {step['seconds']} s.", "", "**Answer**", ""]
            out += [reply.get("answer") or short(reply), ""]
            calls = reply.get("tool_calls") or []
            out += ["**Tool calls**", ""] + [f"- `{c['name']}` {short(c.get('arguments'), 300)} → {c.get('status')}" for c in calls] + [""]
            check = reply.get("answer_check") or {}
            out += [f"**Answer check**: checked {check.get('checked')}, unverified {check.get('unverified')}, retried {check.get('retried')}", ""]
            for proposal in reply.get("proposals") or []:
                out += [f"**Proposal** {proposal.get('kind')} {proposal.get('status')}: {proposal.get('summary')}", ""]
            refs = (reply.get("evidence") or {}).get("refs") or []
            out += [f"**Cited rows**: {[(r.get('source', '').split('/')[-1], r.get('row')) for r in refs][:30]}", ""]
        elif kind == "state":
            out += [f"## Step {number}: application state", ""] + state_lines(step.get("state", {})) + [""]
        else:
            detail = {k: v for k, v in step.items() if k not in ("step", "seconds")}
            out += [f"## Step {number}: {kind}", "", short(detail, 1500), ""]
        if step.get("exception"):
            out += ["**Exception**", "", "```", step["exception"], "```", ""]
    return "\n".join(out)


def main():
    folder = Path(sys.argv[1])
    target = folder / "transcripts"
    target.mkdir(exist_ok=True)
    index = ["# Transcripts", ""]
    for path in sorted((folder / "scenarios").glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        (target / f"{record['scenario']}.md").write_text(render(record), encoding="utf-8")
        index.append(f"- [{record['scenario']}](./{record['scenario']}.md): {', '.join(record['questions'])}")
    (target / "README.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    print(f"rendered {len(index) - 2} scenarios into {target}")


if __name__ == "__main__":
    main()
