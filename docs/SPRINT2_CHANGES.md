# Sprint 2 Changes

Branch `integration/sprint2-base` · 17–26 October 2026 · Group 20, Track 1 (Manager Co-Pilot)

This document lists every change on the integration branch since the four GitHub branches it started
from. It is written for teammates who have not seen the local work: what changed, why, how it was
checked, and what is still open. Issue codes such as `C-1` refer to the team's integration issue list;
each one is also described here in words.

---

## 1. Summary

- **Integration.** The four GitHub branches (`main`, `src`, `data`, `feature/frontend-shell`) and the
  10/22 backend update are merged into one runnable project. Teammates' commits keep their authors.
- **Frontend and backend are connected end to end.** Every page reads live data from the backend:
  chat, morning briefing, orders and output, follow-up actions, watches and alerts.
- **All five Track 1 capabilities work:**
  - a scheduled briefing (structured, plus three sentences of prose);
  - multi-turn Q&A with fresh tool calls and clickable sources;
  - standing watches that raise alerts on their own;
  - feasibility estimates that now account for current load;
  - confirmed, logged actions: reminders, order notes and chase-up drafts.
- **Size.**
  - Backend: 32 agent tools, 32 HTTP endpoints and 8 static Skills.
  - Frontend: 5 pages.
  - Tests: 203 automated tests.
  - Evaluation: a 30-case held-out set and a 17-case development set, with a runner.
- **Still open** (details in section 10):
  - C must review the new current-load and cheapest-plan rules.
  - No run with a real model yet: an API key is pending.
  - The evaluation cases are drafts until each owner reviews them.
  - The repository must be made public before the Sprint 2 upload.

## 2. How to run it

Backend (Python 3.12):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest            # 203 tests, no API key needed
python main.py --api        # real model: put DEEPSEEK_API_KEY or OPENAI_API_KEY in backend/.env
python demo_backend.py      # no key: a keyword demo model drives the real tools (answers start with [demo model])
```

Frontend (Node 18+), in a second terminal:

```bash
cd frontend
npm ci
npm run dev                 # http://localhost:5173, proxies /api/* to the backend on port 8000
```

Evaluation, from the repository root:

```bash
backend/.venv/bin/python evaluation/run_evaluation.py --check                 # validate the case files
backend/.venv/bin/python evaluation/run_evaluation.py --fake                  # offline plumbing check
backend/.venv/bin/python evaluation/run_evaluation.py --set development       # real model, tuning set
```

Never commit `backend/.env`. While the backend runs, `http://127.0.0.1:8000/docs` lists every endpoint.

## 3. Starting point and integration (17–23 October)

| GitHub branch | Author | What it contributed |
|---|---|---|
| `main` | Shilong Zhang | README and the Track 1 implementation plan |
| `src` (c92f85f, then 4e523ba on 10/22) | hzw | Backend prototype: data loader, rules, read-only tools, discovery, briefing, feasibility estimators and optimizer, LangChain agent, FastAPI, terminal app. The 10/22 update added `query_orders`, follow-ups about "these orders", multi-order outsourcing plans with revision, the terminal menu, session titles and saved-key startup |
| `data` | hzw | The three Track 1 CSVs |
| `feature/frontend-shell` (PR #2) | Yukii | React + TypeScript frontend shell: briefing, chat, evidence drawer, confirmation dialog |

Integration changes:

- Backend modules moved under `backend/`; the CSVs under `backend/track1/data/`. The CSVs are byte-for-byte
  identical to the course's `Data_v3` files.
- The MySQL session store became SQLite (`storage.SQLiteStore`, same interface), so the project runs
  with no database server.
- Added a pytest suite, `.env.example`, `.gitignore` rules and README run instructions.
- Merges keep every teammate commit and its author.

## 4. Backend changes

### 4.1 Morning briefing

- `GET /briefings/latest` serves the briefing live. It is built from the tools with no model call, so it is
  deterministic and never stale. The scheduler also saves a dated copy every morning (`GET /briefings`).
- **Every finding has a level, and each level states its rule.**
  - *Act now*: an order late or idle for 7+ days; a stage whose output is down 20%+ (last 3 workdays
    against the previous 7); a customer whose unfinished orders are all late or idle.
  - *Watch*: any other at-risk order.
  - For 1 April: 12 orders at risk, 8 items to act on now, 6 to watch.
- **Yesterday's output** per stage is compared with each stage's 7-workday average. A Monday briefing
  reports the last workday (Saturday) and labels it so. This was issue H-1.
- **Narrative.** The briefing opens with three sentences, in the order the track asks for: what happened
  yesterday, what is at risk, what needs action today. They use the same tool outputs and rules as the
  rest of the page, so they add no numbers of their own. Each sentence carries its source rows.
- The agent's briefing tool result keeps only the narrative's text, because its source rows already
  appear in the sections above it.

### 4.2 Chat with evidence

Every chat answer now returns:

- `tool_calls`: the tools called, with their arguments and status;
- `evidence`: the source rows behind the answer, as `{source, row, key, id}` refs plus the raw CSV rows.
  An `id` such as `orders.csv:86` opens one row through `GET /evidence/{id}`;
- `proposals`: any follow-ups the agent proposed in that turn;
- `prompt_version`: which Skill text produced the answer.

Conversation history carries the same details, so reopening a chat shows its sources again.
Multi-order plans now cite the order and workshop rows they use; before, they cited nothing.

### 4.3 Order lookup that asks instead of guessing

- Order IDs are understood in any spelling: `ORD-002`, `ord002`, `ord 2`, `2`.
- Customer names can be partial. A unique match is used and the answer says how the name was read; an
  ambiguous or unknown name returns candidates.
- A new tool, `search_orders`, and an endpoint, `GET /orders/search`, find candidates by order ID,
  customer, product or stage. An unknown order returns close candidates, and the Skills tell the agent
  to ask which one is meant.

### 4.4 Confirmed actions and audit log

New modules: `actions.py` (store and state machine) and `action_tools.py` (agent tools).

- **Four kinds of follow-up**: reminder, order note, chase-up draft, standing watch.
- **Lifecycle**:
  - The agent or the UI *proposes* a follow-up.
  - Only the manager's Confirm in the app *executes* it.
  - A proposal can also be cancelled, fail, or expire after 24 hours.
  - The agent has no confirm tool.
- **Confirm is idempotent.** Confirming twice returns the first result and does nothing more; this is
  enforced inside one database transaction.
- **Audit log.** Every step is recorded with its actor (agent, user, system or scheduler).
  The log is append-only.
- **What follow-ups can and cannot do.** Chase-up drafts are saved as drafts and never sent; there is no
  send tool. Notes live in the app database and are never written to the course CSVs.
- **Reminder times** use the real calendar in Singapore time ("tomorrow 09:00", "friday 3pm", "in 2 hours").
  Past times and times more than a year ahead are refused.

### 4.5 Standing watches and alerts

- **Four conditions**: an order has not moved by a date, becomes overdue, is completed, or reaches a stage.
- **Scripted data snapshots.** The course data never changes, so watches are checked against versioned,
  scripted snapshots in `backend/track1/scenarios/watch_snapshots.json`:
  - v0: the course data on 1 April;
  - v1 (2 April): ORD-107 completes; ORD-120 and ORD-108 move to WASHING;
  - v2 (3 April): ORD-062 moves to ASSEMBLY, ORD-002 to PACKING and ORD-108 to PACKING; ORD-114 completes.

  `POST /dev/data/advance` and `/dev/data/reset` step through them for demos.
- **Watches that could never fire are refused**: an order that is already complete, a deadline that has
  already passed, or a stage the order has already reached.
- **Alerts.** A met condition raises one alert (deduplicated) and the watch becomes Triggered. Watches can
  be paused, resumed or cancelled.

### 4.6 Scheduler

APScheduler, timezone Asia/Singapore, started by `python main.py --api`. Its jobs:

- the morning briefing at 07:00, once per date even across restarts;
- due reminders, every minute;
- watch checks, every `WATCH_CHECK_MINUTES` (default 1);
- expiry of stale proposals, every 10 minutes.

On startup it catches up on missed runs. A failed job is written to the audit log. `GET /scheduler`
shows its state. The settings are in `.env.example`.

### 4.7 Static Skills

- The single long system prompt became eight Skill files in `backend/skills/`:
  - base grounding policy;
  - morning briefing;
  - general Q&A;
  - order status;
  - feasibility;
  - standing watch;
  - action proposal;
  - unsupported request.
- Each file states when it applies and which tools it may use, and `skills.py` composes them in a fixed
  order. The earlier rules were kept word for word.
- New rules:
  - ask when a reference is ambiguous;
  - propose only, never claim a follow-up is done;
  - reminders use the real calendar, watch deadlines the dataset calendar;
  - decline unsupported requests;
  - terminal shortcuts apply in the terminal app only, and web users find past chats under Recent.
- A test checks that every tool belongs to a Skill.

### 4.8 Feasibility

- **Current load (C-1, to be reviewed by C).**
  - Before: in-house estimates assumed an empty line.
  - The rule: by default, a new in-house batch waits at each stage for the unfinished orders that still
    have to pass through it. Each order counts in full from its current stage, because progress within a
    stage is not recorded. The load is therefore an upper bound, and the date a late estimate.
  - The load on 1 April: about 11 workdays at KNITTING (9,900 pieces), 44 at ASSEMBLY (20,500),
    40 at WASHING (28,850) and 51 at PACKING (32,850).
  - Result: 800 pieces now finish in-house on **1 June**, not 8 April.
  - Starting later does not make the load disappear, because the line keeps working through it. For a
    start date before 1 April no order statuses are known, so no load is applied, and the output says so.
  - A queue in workdays given by the manager (`queue_workdays`) still replaces the load with one flat
    queue. The fastest and cheapest plans use the same queue.
- **Cheapest plan (C-2, to be reviewed by C).**
  - Before: in-house cost is not in the data, so it counted as zero and the cheapest plan always chose
    in-house.
  - Now the cheapest plan compares outside workshops only and says so. Given `in_house_cost_per_piece`,
    in-house competes at that cost, and the assumed in-house cost is reported separately.
  - Asking for in-house without a cost returns `needs_assumption` instead of pricing it at zero.
  - Example: 800 TOPS within 25 days goes to W3 BudgetWorks, finishes 13 April and costs 640.
  - The fastest plan for 800 TOPS now goes fully outside: W8 300, W6 390 and W2 110 pieces, by 6 April,
    for 911.
- **Inputs.** Pieces are limited to 1,000,000, queues to 365 workdays and baselines to 77 workdays.
  Workshop eligibility is checked even for 0 pieces. The optimizer keeps an `insufficient_data` status
  instead of a generic error (H-12, H-15).
- **Rules still for the author and C.** These are unchanged: the W8 batch cap is treated as an
  order cap (H-10), and multi-order "fastest" plans do not pick the cheapest mix on the same date
  (H-11).

### 4.9 API contract and errors

- **One error shape.** Every error is `{detail, code}`: `detail` for people, `code` for programs.
  A not-found order also lists `candidates`.

  | Code | HTTP | Meaning |
  |---|---|---|
  | `SESSION_NOT_FOUND`, `NOT_FOUND` | 404 | Unknown conversation, order, proposal, row or route |
  | `CONFLICT`, `ACTION_STATE` | 409 | Concurrent write, or a proposal that is no longer pending |
  | `INVALID_REQUEST` | 400 | Bad input, with a readable sentence |
  | `AGENT_INCOMPLETE` | 502 | The agent hit its step limit |
  | `MODEL_UNAVAILABLE` | 503 | Model API problem: key, quota, network |
  | `DATABASE_ERROR` | 503 | Local SQLite problem |
  | `INTERNAL_ERROR` | 500 | A bug; the traceback is logged |

  Before this change, any `KeyError` became "Session not found" and every other failure became 503
  "Service unavailable" (H-8, A-3).
- **Read-only endpoints from the plan's API contract (A-2)**: `GET /orders/{id}`,
  `GET /production/stages/{stage}`, `GET /feasibility/estimators`, `POST /feasibility/estimate` and
  `GET /evidence/{file:line}`. They call the agent's own tools, so the numbers match the chat.
- **Tool errors are separated.** `execute_tool` tells invalid arguments apart from tool bugs; bugs are
  logged and reported to the model as failures, never as answers (H-5).
- **Other fixes**: the risk tool returns its numeric thresholds (H-2), and snapshot dates are compared as
  dates rather than strings (H-3).

### 4.10 Model settings

The DeepSeek settings were checked against DeepSeek's documentation on 24 October (D-4):

- `deepseek-flash` is a current model ID and supports tool calls.
- Thinking mode stays off: with tools on, DeepSeek requires its `reasoning_content` to be sent back,
  which LangChain does not do.
- `parallel_tool_calls` is not a documented DeepSeek parameter, so it is now sent to OpenAI only.

A real call with a key is still needed to confirm.

### 4.11 Demo backend

`backend/demo_backend.py` runs the real API, tools, actions, scheduler and SQLite with a rule-based demo
model in place of the LLM. The whole UI can be tried without an API key. Its answers say nothing about
real model quality.

## 5. Frontend changes

- **Layout.** A sidebar with focused pages: New chat (home), Briefing, Orders & output, Actions,
  Watches & alerts, plus recent conversations. Addresses use `#/` routes; a page refresh restores the
  open conversation.
- **Home.** A one-line digest ("12 orders at risk · 8 to act on now"), a centred chat box and suggested
  questions.
- **Briefing page.** The layout follows a daily production report:
  - a headline, then the three narrative sentences, each of which opens its source rows;
  - yesterday's output per stage as tiles: pieces, change against average, a sparkline drawn from zero;
  - findings grouped by check (Production, Orders at risk, Customers), each group under a level header
    that states its rule.
  - The marks are a red circle for *Act now* and an amber triangle for *Watch*. Shape plus colour keeps
    them distinguishable for colour-blind readers, and the colours were checked with a validator.
  - Long groups fold behind "Show all".
  - If the backend is unreachable, the page falls back to a saved snapshot and says so.
- **Chat.**
  - Answers render as safe Markdown (paragraphs, lists, tables, code, links; no raw HTML).
  - Proposals appear as cards with Cancel and Confirm.
  - "Sources (N)" opens the evidence drawer with the tool calls and raw rows.
  - Retry resends a message whose send failed (F-3).
- **Actions page.**
  - Items waiting for confirmation.
  - Reminders (with Dismiss), notes, and chase-up drafts with Copy.
  - A history of every audit event.
- **Watches & alerts page.**
  - Alerts with Mark read; watches with Pause, Resume and Cancel; a New watch dialog.
  - A pill showing which scripted snapshot is loaded, plus Load next snapshot and Reset for demos.
- **Reminder dialog.**
  - Searches any order: by ID in any spelling, customer, product or stage.
  - Has a When field (default tomorrow 09:00, Singapore time).
  - Saves only on Confirm.
- **Other.**
  - A Light / Dark / Match system switch in the sidebar footer, applied before first paint.
  - Mobile layout down to 375 px with no horizontal scroll.
  - Follow-up counts in the sidebar refresh every 30 seconds.

## 6. Evaluation (draft)

- **Case sets.**
  - `evaluation/evaluation_set.jsonl`: 30 held-out cases in 40 turns, 5 per owner (A–F).
  - `evaluation/development_set.jsonl`: 17 cases in 22 turns, for tuning.
  - Coverage in the held-out set: 6 ambiguous, unanswerable or hallucination-bait cases; 10 feasibility or
    action cases; 8 multi-turn cases.
  - The questions already used to tune the prompt by hand are in the development set only.
- **What each case defines**: the expected behaviour per turn (answer, clarify, decline or propose), facts
  that must and must not appear, the required tools and arguments, the required source rows, and
  behaviour checks such as "asks for confirmation" or "no guarantee".
- **How the answers were verified.** Every expected fact was computed with the tools, then recomputed from
  the raw CSVs by a separate script that imports no backend code. All agree. Feasibility cases are scored
  on behaviour only, because the C-1/C-2/H-10/H-11 rules can move their dates and costs.
- **The runner.** `evaluation/run_evaluation.py` runs each case through the real `ChatService` on a fresh
  temporary database. It scores the plan's §13.4 metrics and §13.5 quality gates, and records versions:
  commit, data and case-file hashes, model, prompt version. Failures go to `failure_ledger.jsonl` with the
  root-cause fields left for people to fill in.
- **Limits.** Behaviour labels come from text rules, so reviewers should read failures, and a sample of
  passes too. `--fake` only checks the plumbing; its scores mean nothing.
- **Status.** Every case is a draft until another member verifies it (see `evaluation/README.md`). The
  first real-model run waits for an API key.

## 7. Tests and verification

- **Automated tests**: 203 pytest tests across tools, rules, the briefing, storage, the API and its
  errors, actions and idempotency, watches, the scheduler, Skills, evidence refs, read-only views,
  feasibility inputs and current load, model settings, the demo backend and the evaluation runner. The
  frontend passes `tsc` and `vite build`.
- **Independent recomputation.**
  - Read-only tools were checked against a separate recomputation from the raw CSVs: 5 dates,
    576 baseline comparisons and 120 order traces, all equal.
  - The feasibility code was checked against a reference model in about 3,900 scenarios, with no mismatch.
  - The new current-load dates were recomputed the same way.
- **Clean checkout.** Tests, the evaluation check and the frontend build pass from a fresh clone,
  reusing installed dependencies.
- **Browser checks** on separate ports:
  - each chat flow: proposal, confirm, sources, retry;
  - watch → snapshot → alert;
  - briefing levels and narrative;
  - mobile and dark mode;
  - the offline fallback.

## 8. HTTP endpoints

The frontend reaches these as `/api/...` through the Vite proxy.

| Area | Endpoints |
|---|---|
| Conversations | `GET/POST /sessions`, `GET/POST /sessions/{id}/messages` |
| Briefing | `GET /briefings/latest`, `GET /briefings`, `POST /dev/briefings/generate` |
| Orders and data | `GET /orders/search`, `GET /orders/{id}`, `GET /production/stages/{stage}`, `GET /evidence/{file:line}` |
| Feasibility | `GET /feasibility/estimators`, `POST /feasibility/estimate` |
| Follow-ups | `GET /actions`, `POST /actions/proposals`, `POST /actions/{id}/confirm`, `POST /actions/{id}/cancel`, `GET /follow-ups/counts`, `GET /reminders`, `POST /reminders/{id}/dismiss`, `GET /notes`, `GET /drafts`, `GET /audit` |
| Watches and alerts | `GET /watches`, `GET /watches/{id}`, `POST /watches/{id}/{pause\|resume\|cancel}`, `GET /alerts`, `POST /alerts/{id}/read` |
| Demo data and scheduler | `GET /data/snapshot`, `POST /dev/data/advance`, `POST /dev/data/reset`, `GET /scheduler` |

## 9. Agent tools (32)

| Kind | Tools |
|---|---|
| Retrieval | `get_order_status`, `get_customer_orders`, `query_orders`, `search_orders`, `get_overdue_orders`, `get_stage_output` |
| Judgement | `compare_stage_output`, `get_orders_at_risk` |
| Tracing | `trace_order` (plus source refs on every result) |
| Discovery and briefing | `discover_issues`, `get_morning_briefing` |
| Feasibility | `estimate_in_house`, `estimate_production_plan`, eight per-workshop estimators (`estimate_quickstitch` … `estimate_freshstart`), `optimize_fastest_plan`, `optimize_cheapest_plan`, `optimize_orders_outsourced`, `optimize_orders_cheapest`, `revise_order_plan`, `get_current_plan` |
| Action (propose only) | `propose_reminder`, `propose_order_note`, `draft_chase_message`, `propose_watch`, `list_follow_ups` |

## 10. Open items and known limitations

- **For C to review**:
  - the current-load rule (C-1): whether counting each order in full from its current stage is an
    acceptable upper bound, and whether new orders should queue by due date rather than behind all
    existing work;
  - the cheapest-plan rule (C-2);
  - whether the fastest plan should still break date ties by treating in-house as free.
- **Still with the author and C**:
  - the W8 batch cap (H-10);
  - same-date cost in multi-order fastest plans (H-11);
  - the rounding description (H-13);
  - workshop queues for later start dates (H-14; the in-house part is handled);
  - day-count wording (H-16);
  - the 25 March step in assembly output, which affects baselines (C-3).
- **Not done yet**:
  - responses have no declared schemas, so frontend types are kept in sync by hand (H-7);
  - the full history, including old tool results, is resent to the model every turn, which costs tokens
    and grows the context (D-2, linked to N-2);
  - no real-model run yet (D-4);
  - voice input and output (optional in the track) is not implemented.
- **Before Sprint 2 (30 October)**:
  - make the repository public;
  - add a demo link;
  - replace the A–F placeholders in the README with names;
  - run the development set with a real model before recording the demo.
- **For the final submission**:
  - the formal tool specification table (input, output, purpose, non-goals and failure mode for every
    tool, and the worst case for each action tool);
  - Documentation.pdf and Evaluation.pdf, including at least 10 analysed failures.

## 11. Commits on this branch

**17 October — integration**

| Commit | Change |
|---|---|
| `5e7697c`, `9721f5b`, `c9843bc` | Merge the frontend shell, the backend prototype and the CSVs |
| `ef0d70b` | Move backend modules and CSVs under `backend/` |
| `187707b` | Replace the MySQL session store with SQLite |
| `53c67d2` | Add the pytest suite, `.gitignore` rules and `.env.example` |
| `582e59b` | Document the layout, run steps and implementation status |

**23 October — 10/22 update, live briefing and UI**

| Commit | Change |
|---|---|
| `83abb35`, `abf7060` | Merge hzw's 10/22 backend update; document it |
| `ef0b260`, `cf95b65`, `53aa0f5` | `GET /briefings/latest`; the frontend loads the briefing live |
| `200f9a1` | Sidebar layout with focused pages |
| `5fc3431`, `a233857` | `GET /orders/search`; calmer visual system; reminder dialog that searches any order |
| `dfca9b4` … `6b6a076` | Briefing iterations, ending with *Act now* / *Watch* levels and rules on the page, and yesterday's output tiles |
| `7ad53ac` | Light / Dark / Match system switch |

**24 October — review fixes and missing features**

| Commit | Change |
|---|---|
| `72dd3b8`, `a8e7a01` | Review fixes H-1, H-2, H-3, H-5, H-8, H-9, H-12, H-15 |
| `0dcec5a` | Confirmed follow-ups, watches, scheduler, chat evidence, order lookup, Skills |
| `764300a` | Frontend for follow-ups, watches and alerts, chat sources, Markdown |
| `ea7116f` | Web vs terminal navigation in the Skills |
| `f592085` | Read-only endpoints from the API contract |
| `3a7ab70` | Retry resends a failed message |
| `2e441ac` | DeepSeek request parameters per its documentation |
| `3cb8d02`, `8b10d04` | Scheduler settings in `.env.example`; README status |
| `a6bda72` | Sources for multi-order plans; evidence IDs |
| `be265f1` | Evaluation sets and runner (draft) |

**26 October — narrative and current load**

| Commit | Change |
|---|---|
| `5536d91`, `1cc261b` | Briefing narrative (three sentences), full width |
| `a70dcec`, `0e4a8c0` | Feasibility: current load (C-1) and cheapest plan (C-2); README |
| (this commit) | Demo backend in the repository; this document |

## 12. Suggested review by owner

| Owner | Please check |
|---|---|
| A | This document, the README, the evaluation set as a whole, the Sprint 2 slide facts |
| B | Order lookup and candidates (§4.3), evidence refs and `GET /evidence` (§4.2), retrieval tests |
| C | Current load and the cheapest-plan rule (§4.8), briefing levels and rules (§4.1), your five evaluation cases |
| D | The Skills (§4.7), model settings (§4.10), clarify and decline behaviour, your five evaluation cases |
| E | Actions, audit and idempotency (§4.4), watches (§4.5), scheduler (§4.6), your five evaluation cases |
| F | All frontend pages (§5), the demo backend for the video (§4.11), your five evaluation cases |
