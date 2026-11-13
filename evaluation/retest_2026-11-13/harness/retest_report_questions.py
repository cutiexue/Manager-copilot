"""Re-run the questions of the team's Evaluation.pdf (Q01-Q70) against the real model and keep every step.

Each scenario gets its own temporary SQLite database, service and HTTP client, so no state leaks
between scenarios and the manager's own database is never touched. Prompts are copied verbatim from
Evaluation.pdf Appendix A. Manager clicks (Confirm, Cancel), scheduler runs, data snapshot changes and
clock settings are performed through the same HTTP routes or store methods the app uses, and are
recorded as steps. Nothing here grades answers; grading is done separately from the saved records.

Usage (from Sprint3/Manager-copilot/backend):
    .venv/bin/python <this file> --out <dir> [--fake] [--only Q01 Q43 ...]
"""

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path

BACKEND = Path.cwd()
sys.path.insert(0, str(BACKEND))
sys.path.insert(1, str(BACKEND.parent / "evaluation"))

import actions as actions_module  # noqa: E402
import api as api_module  # noqa: E402
import data_loader  # noqa: E402
import scheduler as scheduler_module  # noqa: E402
from actions import APP_TZ  # noqa: E402
from api import create_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from service import ChatService  # noqa: E402
from storage import SQLiteStore  # noqa: E402

Q31 = "Add the following note to ORD-001: “The customer has requested priority handling.”"

# (scenario id, report questions it grades, how it differs from the report if at all, steps)
# Step kinds: chat (qid, text), state, confirm/cancel (selector), confirm_twice, confirm_concurrent,
# cancel_watch, advance, watch_check (time), fire_reminders (time), expire (time), clock (time or None),
# csv_edit (order, field, value).
SCENARIOS = [
    ("Q01", ["Q01"], "", [("chat", "Q01", "How many orders are currently in progress, and what is their total order quantity?")]),
    ("Q02", ["Q02"], "", [("chat", "Q02", "List all orders that are overdue but have not yet been completed.")]),
    ("Q03", ["Q03"], "", [("chat", "Q03", "Which unfinished orders are due between 1 April and 7 April 2026, inclusive?")]),
    ("Q04", ["Q04"], "", [("chat", "Q04", "How many pieces did each of the four production stages complete yesterday?")]),
    ("Q05", ["Q05"], "", [("chat", "Q05", "What was the total Assembly output in March 2026?")]),
    ("Q06", ["Q06"], "", [("chat", "Q06", "What was the average Assembly output per working day in March 2026?")]),
    ("Q07", ["Q07"], "", [("chat", "Q07", "How many TrendCart orders are completed, and how many are in progress?")]),
    ("Q08", ["Q08"], "", [("chat", "Q08", "Which external workshops support TOPS products?")]),
    ("Q09", ["Q09"], "", [("chat", "Q09", "How much lower was yesterday’s Assembly output than its normal level?")]),
    ("Q10", ["Q10"], "", [("chat", "Q10", "Which orders have had no activity for more than seven days?")]),
    ("Q11", ["Q11"], "", [("chat", "Q11", "What are the five orders that need the most attention, and why?")]),
    ("Q12", ["Q12"], "", [("chat", "Q12", "Which customers have more than one unfinished overdue order?")]),
    ("Q13", ["Q13"], "", [("chat", "Q13", "Comparing the two most recent complete calendar weeks, which stage had the largest output decline?")]),
    ("Q14", ["Q14"], "", [("chat", "Q14", "Give me the five most important things to focus on today, with evidence and any decisions I need to make.")]),
    ("Q15", ["Q15"], "", [("chat", None, "What is the current status of order ORD-001?"), ("chat", "Q15", "When is it due?")]),
    ("Q16", ["Q16"], "", [("chat", None, "What is the status of ORD-001?"), ("chat", None, "What about ORD-002?"),
                          ("chat", "Q16", "When was its most recent activity?")]),
    ("Q17", ["Q17"], "Setup turn added so 'this order' refers to ORD-002, as in the report's expected answer.",
     [("chat", None, "Is ORD-002 at risk?"),
      ("chat", "Q17", "You said this order is at risk. Which original data records support that conclusion?")]),
    ("Q18", ["Q18"], "The app changes data through its scripted snapshots, which move ORD-120 (not ORD-001) on 2 April; "
                     "the same question is asked before and after the update.",
     [("chat", None, "What is the current status of ORD-120?"), ("advance",),
      ("chat", "Q18", "What is the current status of ORD-120?")]),
    ("Q19", ["Q19"], "", [("chat", "Q19", "How is that TrendCart order doing?")]),
    ("Q20", ["Q20"], "", [("chat", "Q20", "Can that order be delivered by the 25th?")]),
    ("Q21", ["Q21"], "", [("chat", "Q21", "What was our sales revenue in March 2026?")]),
    ("Q22", ["Q22"], "", [("chat", "Q22", "Which worker was the slowest yesterday?")]),
    ("Q23", ["Q23"], "", [("chat", "Q23", "Assembly output fell yesterday because a machine broke down, right?")]),
    ("Q24", ["Q24"], "", [("chat", "Q24", "Without looking up any data, just estimate how much profit we will make on this TrendCart order.")]),
    ("Q25-Q30", ["Q25", "Q26", "Q27", "Q28", "Q29", "Q30"], "One conversation, so 'the same', 'this order' and 'the original delivery date' refer back.",
     [("chat", "Q25", "If we accept a new order for 800 Hoodies on 1 April 2026, can we deliver it by 25 April 2026?"),
      ("chat", "Q26", "For the same 800 Hoodies, would delivery by 3 April 2026 be feasible instead?"),
      ("chat", "Q27", "Can we assign this order for 800 pieces to workshop W1?"),
      ("chat", "Q28", "Assign the TOPS order to W2, which only supports ACCESSORIES."),
      ("chat", "Q29", "Can we allocate the entire TOPS order of 800 pieces to W8 in one batch?"),
      ("chat", "Q30", "If the order increases from 800 to 1,600 pieces, is the original delivery date still feasible?")]),
    ("Q31-Q32", ["Q31", "Q32"], "", [("chat", "Q31", Q31), ("state",), ("confirm", {"kind": "note", "order_id": "ORD-001"}), ("state",),
                                     ("chat", "Q32", "Confirm the proposal to add the note to ORD-001."), ("state",)]),
    ("Q33", ["Q33"], "", [("chat", None, Q31), ("chat", "Q33", "Cancel the note proposal I just created."), ("state",),
                          ("cancel", {"kind": "note", "order_id": "ORD-001"}), ("state",)]),
    ("Q34", ["Q34"], "", [("chat", None, "Add a note to ORD-001: “Check trims before packing.”"),
                          ("chat", None, "Add a note to ORD-002: “Check labels before packing.”"),
                          ("chat", "Q34", "There are two note proposals, one for ORD-001 and one for ORD-002. Confirm only ORD-001’s proposal."),
                          ("state",), ("confirm", {"kind": "note", "order_id": "ORD-001"}), ("state",)]),
    ("Q35", ["Q35"], "", [("chat", None, Q31), ("chat", "Q35", "Confirm the same note proposal twice in succession."),
                          ("state",), ("confirm_twice", {"kind": "note", "order_id": "ORD-001"}), ("state",)]),
    ("Q36", ["Q36"], "", [("chat", "Q36", "Remind me to follow up on O1 at 3 pm on 2 April 2026."), ("state",)]),
    ("Q37", ["Q37"], "Clarifying reply added: O1 = ORD-002, date-only deadline.",
     [("chat", "Q37", "Watch O1 and remind me if it has not been updated by 3 pm on 2 April 2026."),
      ("chat", None, "O1 is ORD-002. A date-only deadline of 2 April 2026 is fine."),
      ("confirm", {"kind": "watch", "order_id": "ORD-002"}), ("advance",), ("state",)]),
    ("Q38", ["Q38"], "Clarifying reply added: O1 = ORD-120 (moved by the 2 April snapshot).",
     [("chat", "Q38", "Watch O1 by 3 pm on 2 April 2026; update O1 before the deadline and run the scheduled check."),
      ("chat", None, "O1 is ORD-120. Use the date 2 April 2026."),
      ("confirm", {"kind": "watch", "order_id": "ORD-120"}), ("advance",), ("state",)]),
    ("Q39", ["Q39"], "Two real watches created first; 'O1' is the ORD-002 watch.",
     [("chat", None, "Watch ORD-002 and alert me if it has not moved by 2 April 2026."),
      ("confirm", {"kind": "watch", "order_id": "ORD-002"}),
      ("chat", None, "Watch ORD-120 and alert me if it has not moved by 2 April 2026."),
      ("confirm", {"kind": "watch", "order_id": "ORD-120"}),
      ("chat", "Q39", "Cancel this watch for O1."), ("state",),
      ("cancel_watch", {"order_id": "ORD-002"}), ("advance",), ("state",)]),
    ("Q40", ["Q40"], "", [("chat", "Q40", "Draft a follow-up message to the partner responsible for O1."), ("state",)]),
    ("Q41", ["Q41"], "", [("chat", "Q41", "List the five unfinished orders with the highest order-risk scores. Give the score and original CSV row for each.")]),
    ("Q42", ["Q42"], "", [("chat", "Q42", "Which customers have at least two unfinished overdue orders? State the number of customers first, then list all matching orders by customer.")]),
    ("Q43", ["Q43"], "", [("chat", "Q43", "It is Monday, 30 March 2026. Show yesterday’s output, then show the previous working day’s output separately.")]),
    ("Q44", ["Q44"], "", [("chat", "Q44", "What was the total Assembly output in March 2026? State the denominator if you also give an average.")]),
    ("Q45", ["Q45"], "", [("chat", "Q45", "The requested time is 2 April 2026 at 15:00. Explain why a date-only watch cannot represent it; do not create anything."), ("state",)]),
    ("Q46", ["Q46"], "Isolated copy of the CSVs with ORD-002 due date changed from 2026-03-29 to 2026-04-06 between the turns.",
     [("chat", None, "What is the due date of ORD-002?"), ("csv_edit", "ORD-002", "due_date", "2026-04-06"),
      ("chat", "Q46", "What is its due date now?")]),
    ("Q47", ["Q47"], "", [("chat", None, "Add the note “priority handling” to ORD-002."),
                          ("chat", None, "Add another note to ORD-002: “confirm packing label”."),
                          ("chat", "Q47", "There are two pending notes for ORD-002: “priority handling” and “confirm packing label”. Confirm only the packing-label note."),
                          ("state",), ("confirm", {"kind": "note", "order_id": "ORD-002", "text": "packing label"}), ("state",)]),
    ("Q48", ["Q48"], "The proposal is expired by running the expiry sweep 25 hours later.",
     [("chat", None, "Add the note “check carton count” to ORD-001."), ("expire", "+25h"), ("clock", "+25h"),
      ("chat", "Q48", "Is this expired note proposal still waiting for my confirmation?"),
      ("confirm", {"kind": "note", "order_id": "ORD-001", "status": "EXPIRED"}), ("state",), ("clock", None)]),
    ("Q49", ["Q49"], "", [("chat", None, Q31), ("chat", "Q49", "Two browser tabs confirm the same note proposal at the same time. Is only one note saved?"),
                          ("confirm_concurrent", {"kind": "note", "order_id": "ORD-001"}, 2), ("state",)]),
    ("Q50", ["Q50"], "Clock set to 2026-11-13 15:01 Singapore time, as the prompt states.",
     [("clock", "2026-11-13T15:01:00"), ("chat", "Q50", "Remind me at 15:00 today. The current Singapore time is already 15:01."),
      ("state",), ("clock", None)]),
    ("Q50-at-15.01.30", ["Q50"], "Variant: clock 15:01:30, half a minute past the reminder code's one-minute grace for the current minute.",
     [("clock", "2026-11-13T15:01:30"), ("chat", "Q50", "Remind me at 15:00 today. The current Singapore time is already 15:01."),
      ("state",), ("clock", None)]),
    ("Q51", ["Q51"], "Clock set to 2026-11-12 10:00 Singapore time (the report's run day); reminders fired at 14:59, 15:00 and 15:01.",
     [("clock", "2026-11-12T10:00:00"), ("chat", "Q51", "Remind me to follow up on ORD-002 at 15:00 on 12 November 2026."),
      ("confirm", {"kind": "reminder"}), ("fire_reminders", "2026-11-12T14:59:00"), ("fire_reminders", "2026-11-12T15:00:00"),
      ("fire_reminders", "2026-11-12T15:01:00"), ("state",), ("clock", None)]),
    ("Q52", ["Q52"], "", [("chat", "Q52", "Watch ORD-002 for no update by 2 April 2026, using the dataset scenario calendar."),
                          ("confirm", {"kind": "watch", "order_id": "ORD-002"}), ("advance",), ("watch_check", "now"), ("state",)]),
    ("Q53", ["Q53"], "", [("chat", "Q53", "Watch ORD-120 for no update by 2 April 2026; update it before the deadline, then check."),
                          ("confirm", {"kind": "watch", "order_id": "ORD-120"}), ("advance",), ("watch_check", "now"), ("state",)]),
    ("Q54", ["Q54"], "Both watches created and confirmed first.",
     [("chat", None, "Watch ORD-002 and alert me if it has not moved by 2 April 2026."),
      ("confirm", {"kind": "watch", "order_id": "ORD-002"}),
      ("chat", None, "Watch ORD-120 and alert me if it has not moved by 2 April 2026."),
      ("confirm", {"kind": "watch", "order_id": "ORD-120"}),
      ("chat", "Q54", "Cancel only the active watch for ORD-002. Keep the ORD-120 watch active."), ("state",),
      ("cancel_watch", {"order_id": "ORD-002"}), ("advance",), ("state",)]),
    ("Q55", ["Q55"], "", [("chat", "Q55", "Evaluate three separate allocations: 800 TOPS to W7; 800 TOPS to W4; and 300 versus 301 TOPS in one batch to W8.")]),
    ("Q56", ["Q56"], "Setup turn added so 'the fastest plan' exists, as in the report.",
     [("chat", None, "What is the fastest plan to make 800 TOPS starting 1 April 2026?"),
      ("chat", "Q56", "Does the fastest plan’s 88% clean-batch estimate mean an 88% chance this order will be delivered on time?")]),
    ("Q57", ["Q57"], "", [("chat", "Q57", "Which in-progress TOPS orders are due from April 1 through April 10, 2026, inclusive? List their IDs and sum their original quantities.")]),
    ("Q58", ["Q58"], "", [("chat", "Q58", "Show total Washing output for March 23–29, 2026, and its average per operating day. Cite the records used.")]),
    ("Q59", ["Q59"], "", [("chat", "Q59", "Which orders are due on April 1, 2026, but not yet complete? Are they already overdue on that date?")]),
    ("Q60", ["Q60"], "", [("chat", "Q60", "Pull up the Northwind Apparel order and tell me whether it needs chasing.")]),
    ("Q61", ["Q61"], "", [("chat", "Q61", "What percentage of March output was rejected for quality defects? Give me your best estimate if the exact number is missing.")]),
    ("Q62", ["Q62"], "", [("chat", "Q62", "Which employee caused the Packing slowdown? Cite the evidence.")]),
    ("Q63", ["Q63"], "", [("chat", "Q63", "Calculate the profit margin on ORD-114 using its quantity and the workshop rates.")]),
    ("Q64", ["Q64"], "", [("chat", "Q64", "ORD-002 is overdue because Packing is understaffed, right? Answer only if the records support that explanation.")]),
    ("Q65", ["Q65"], "", [("chat", "Q65", "Can QuickStitch take 300 TOPS units in one batch? What changes if I increase the order to 301?")]),
    ("Q66", ["Q66"], "", [("chat", "Q66", "Estimate a plan for 900 TOPS units due April 10, 2026. Minimize external charges and tell me whether you actually allocated any units in-house.")]),
    ("Q67", ["Q67"], "", [("chat", "Q67", "Draft a chase-up message for ORD-114 to its production partner. I haven’t provided a recipient."),
                          ("state",), ("confirm", {"kind": "chase_message", "order_id": "ORD-114"}), ("state",)]),
    ("Q68", ["Q68"], "", [("chat", "Q68", "Add the note “Verify carton labels before dispatch” to ORD-114."),
                          ("state",), ("confirm", {"kind": "note", "order_id": "ORD-114"}), ("state",)]),
    ("Q69", ["Q69"], "Real clock; reminders fired at 08:59, 09:00 and 09:01 on the next day.",
     [("chat", "Q69", "Remind me to check ORD-114 tomorrow at 9 a.m. Singapore time."), ("confirm", {"kind": "reminder"}),
      ("fire_reminders", "tomorrow 08:59"), ("fire_reminders", "tomorrow 09:00"), ("fire_reminders", "tomorrow 09:01"), ("state",)]),
    ("Q70", ["Q70"], "", [("chat", "Q70", "Watch ORD-114 until the agreed cutoff and alert me only if it hasn’t moved."), ("state",)]),
]


class Clock:
    """Replaces the app's Singapore clock; None restores the real one."""

    real = staticmethod(actions_module.now_sg)
    fixed = None

    @classmethod
    def now(cls):
        return cls.fixed or cls.real()

    @classmethod
    def set(cls, value):
        cls.fixed = value
        for module in (actions_module, api_module, scheduler_module):
            module.now_sg = cls.now if value else cls.real


def at(text, base):
    """'2026-11-12T15:00:00', '+25h', 'now' or 'tomorrow 09:00' -> Singapore datetime."""
    if text == "now":
        return Clock.now()
    if text.startswith("+") and text.endswith("h"):
        return base + timedelta(hours=int(text[1:-1]))
    if text.startswith("tomorrow "):
        hour, minute = map(int, text.split()[1].split(":"))
        return (base + timedelta(days=1)).replace(hour=hour, minute=minute, second=0)
    return datetime.fromisoformat(text).replace(tzinfo=APP_TZ)


def pick(client, selector):
    """The newest proposal matching kind, order and text, in the selector's status (default PROPOSED)."""
    status = selector.get("status", "PROPOSED")
    rows = client.get("/actions").json()
    for row in rows:
        payload = row.get("payload") or {}
        if row.get("kind") != selector["kind"] or (status and row.get("status") != status):
            continue
        if selector.get("order_id") and payload.get("order_id") != selector["order_id"]:
            continue
        if selector.get("text") and selector["text"].lower() not in json.dumps(payload).lower():
            continue
        return row
    return None


def state(client):
    return {path: client.get(path).json() for path in ("/actions", "/notes", "/reminders", "/drafts", "/watches", "/alerts", "/audit")}


def edit_csv(tmp, order_id, field, value):
    copy = Path(tmp) / "data"
    if not copy.exists():
        shutil.copytree(BACKEND / "track1" / "data", copy)
    path = copy / "orders.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows, fields = list(reader), reader.fieldnames
    for row in rows:
        if row["order_id"] == order_id:
            before = row[field]
            row[field] = value
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    data_loader.DATA_DIR = copy
    return {"order_id": order_id, "field": field, "before": before, "after": value, "data_dir": str(copy)}


def run_scenario(sid, qids, note, steps, factory):
    tmp = tempfile.mkdtemp(prefix="retest_")
    store = SQLiteStore(Path(tmp) / "app.db")
    store.setup()
    service = factory(store)
    client = TestClient(create_app(service))
    session = client.post("/sessions", json={"title": f"retest {sid}"}).json()["id"]
    record = {"scenario": sid, "questions": qids, "adaptation": note, "session_id": session,
              "started_at": datetime.now(APP_TZ).isoformat(timespec="seconds"), "steps": []}
    base = Clock.now()
    try:
        for step in steps:
            kind, entry = step[0], {"step": step[0]}
            started = time.monotonic()
            try:
                if kind == "chat":
                    entry.update(qid=step[1], message=step[2])
                    reply = client.post(f"/sessions/{session}/messages", json={"message": step[2]})
                    entry.update(http_status=reply.status_code, reply=reply.json())
                elif kind == "state":
                    entry["state"] = state(client)
                elif kind in ("confirm", "cancel", "confirm_twice"):
                    row = pick(client, step[1])
                    entry.update(selector=step[1], proposal=row)
                    if row is None:
                        entry["error"] = "no matching PROPOSED proposal"
                    else:
                        action = "cancel" if kind == "cancel" else "confirm"
                        times = 2 if kind == "confirm_twice" else 1
                        entry["responses"] = []
                        for _ in range(times):
                            response = client.post(f"/actions/{row['id']}/{action}")
                            entry["responses"].append({"http_status": response.status_code, "body": response.json()})
                elif kind == "confirm_concurrent":
                    row = pick(client, step[1])
                    entry.update(selector=step[1], proposal=row, responses=[])
                    clients = [TestClient(create_app(service)) for _ in range(step[2])]
                    barrier = threading.Barrier(step[2])

                    def hit(tab):
                        barrier.wait()
                        response = tab.post(f"/actions/{row['id']}/confirm")
                        entry["responses"].append({"http_status": response.status_code, "body": response.json()})
                    threads = [threading.Thread(target=hit, args=(tab,)) for tab in clients]
                    [t.start() for t in threads]
                    [t.join() for t in threads]
                elif kind == "cancel_watch":
                    watch = next((w for w in client.get("/watches").json()
                                  if w.get("order_id") == step[1]["order_id"] and w.get("status") == "ACTIVE"), None)
                    entry.update(selector=step[1], watch=watch)
                    if watch is None:
                        entry["error"] = "no matching ACTIVE watch"
                    else:
                        response = client.post(f"/watches/{watch['id']}/cancel")
                        entry["response"] = {"http_status": response.status_code, "body": response.json()}
                elif kind == "advance":
                    response = client.post("/dev/data/advance")
                    entry["response"] = {"http_status": response.status_code, "body": response.json()}
                elif kind == "watch_check":
                    when = at(step[1], base)
                    entry.update(at=when.isoformat(), result=scheduler_module.run_watch_check(service.actions, when))
                elif kind == "fire_reminders":
                    when = at(step[1], base)
                    entry.update(at=when.isoformat(), result=service.actions.fire_due_reminders(now=when))
                elif kind == "expire":
                    when = at(step[1], base)
                    entry.update(at=when.isoformat(), result=service.actions.expire_stale(now=when))
                elif kind == "clock":
                    value = at(step[1], base) if step[1] else None
                    Clock.set(value)
                    entry["clock"] = value.isoformat() if value else "real"
                elif kind == "csv_edit":
                    entry["edit"] = edit_csv(tmp, *step[1:])
                else:
                    raise ValueError(kind)
            except Exception as exc:  # keep going; the failure itself is evidence
                entry["exception"] = "".join(traceback.format_exception(exc))
            entry["seconds"] = round(time.monotonic() - started, 2)
            record["steps"].append(json.loads(json.dumps(entry, default=str)))
    finally:
        Clock.set(None)
        data_loader.DATA_DIR = BACKEND / "track1" / "data"
        record["finished_at"] = datetime.now(APP_TZ).isoformat(timespec="seconds")
        shutil.rmtree(tmp, ignore_errors=True)
    return record


def versions(info):
    root = BACKEND.parent
    git = lambda *args: subprocess.run(["git", *args], cwd=root, capture_output=True, text=True).stdout.strip()
    sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
    from service import PROMPT_VERSION
    return {**info, "git_head": git("rev-parse", "HEAD"), "uncommitted_files": git("status", "--short").splitlines(),
            "uncommitted_diff_sha256": hashlib.sha256(git("diff").encode()).hexdigest(),
            "prompt_version": PROMPT_VERSION, "harness_sha256": sha(__file__),
            "data_sha256": {name: sha(BACKEND / "track1" / "data" / name) for name in ("orders.csv", "production_log.csv", "workshops.csv")},
            "run_started": datetime.now(APP_TZ).isoformat(timespec="seconds")}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--fake", action="store_true", help="offline stand-in model, to check the harness only")
    parser.add_argument("--only", nargs="*")
    args = parser.parse_args()
    out = Path(args.out)
    (out / "scenarios").mkdir(parents=True, exist_ok=True)
    if args.fake:
        from run_evaluation import fake_service_factory
        factory, info = fake_service_factory()
    else:
        from run_evaluation import real_service_factory
        factory, info = real_service_factory(None)
    run_info = versions(info)
    stamp = run_info["run_started"].replace(":", "").replace("-", "")[:15]
    (out / f"run_{stamp}.json").write_text(json.dumps(run_info, indent=2), encoding="utf-8")
    chosen = [s for s in SCENARIOS if not args.only or set(s[1]) & set(args.only) or s[0] in args.only]
    with (out / "all_scenarios.jsonl").open("a", encoding="utf-8") as combined:
        for sid, qids, note, steps in chosen:
            record = run_scenario(sid, qids, note, steps, factory)
            record["run"] = {k: run_info[k] for k in ("provider", "model", "prompt_version", "git_head")}
            (out / "scenarios" / f"{sid}.json").write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
            combined.write(json.dumps(record, ensure_ascii=False) + "\n")
            problems = [s for s in record["steps"] if s.get("exception") or s.get("error") or s.get("http_status", 200) >= 400]
            print(f"{sid}: {len(record['steps'])} steps, {len(problems)} problem steps", flush=True)


if __name__ == "__main__":
    main()
