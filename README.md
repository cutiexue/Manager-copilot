# Manager Co-Pilot

DSS5105 Capstone Project — **Track 1: The General Manager's Co-Pilot**

Manager Co-Pilot is an AI-assisted decision-support system for factory general managers. It helps users understand current operations, identify risks, estimate feasibility, and take controlled actions based on traceable production data.

> **Current phase:** Sprint 3 — all six workflows are built, with local reliability fixes described in [Final fixes](./docs/FINAL_FIXES_2026-11-11.md). Historical real-model runs passed all automated checks in 29/30 evaluation-suite and 15/17 development cases. These are provisional development results: labels await independent review, and the current code/Skills have not yet been rerun with a real model. See [Evaluation](./evaluation/README.md).

## Quick Start

Requires Python 3.12 and Node.js 22.6+ (use the latest Node 22 patch for the included frontend tests).

**Windows, one click:** double-click `start_app.bat`. It sets things up on the first run, starts the
backend and the frontend in two windows and opens http://localhost:5173. Close the two windows to stop.
The manual steps are below. Use `start_app.bat --demo` for the keyword demo model without an API key.
After pulling dependency changes, run `start_app.bat --setup` (optionally with `--demo`) to refresh
the environments. A failed setup is not marked ready. The launcher never deletes source files.

```text
Manager-copilot/
├── start_app.bat            # Windows: set up on first run, start backend + frontend, open the browser
├── run_evaluation.bat       # Windows: tests, then offline checks; --real explicitly uses the model API
├── backend/                 # FastAPI + LangChain agent + deterministic tools (module map: backend/README.md)
│   ├── skills/              # static Skills (Markdown), composed into the system prompt
│   ├── track1/data/         # read-only course CSVs (orders, production_log, workshops) and their data dictionary
│   ├── track1/scenarios/    # scripted, versioned data snapshots for standing watches and demos
│   └── tests/               # pytest suite, no API key needed
├── frontend/                # React + TypeScript + Vite (see frontend/README.md)
├── evaluation/              # question sets, runner, failure ledger and real-model reports
└── docs/                    # implementation plan and sprint change logs
```

Backend and tests:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python -m pytest          # tools, SQLite store, chat + briefing API with a fake agent
python main.py --local    # one order lookup, no LLM call
python main.py            # terminal menu: conversations, history, on-demand briefing
python main.py --api      # serves 127.0.0.1:8000 for the frontend and starts the scheduler
python demo_backend.py    # same API without an API key: a keyword demo model drives the real tools
```

Both `main.py` modes use the provider and API key saved in `backend/.env` (see `backend/.env.example`) or the environment, and only ask for the key when none is set. `--provider deepseek|openai` overrides `LLM_PROVIDER`.

Frontend (second terminal):

```bash
cd frontend
npm ci                    # installs exactly what package-lock.json pins
npm run dev               # http://localhost:5173, proxies /api/* to the backend
```

Chat sessions, follow-ups, watches, alerts and the audit log are stored in `backend/manager_copilot.db` (SQLite, git-ignored). Never commit `.env`. While the backend runs, the API is described at http://127.0.0.1:8000/docs.

## Implementation Status

| Workflow / layer | Status | Where |
|---|---|---|
| Retrieval, judgement, tracing, discovery tools | Built, read-only, tested; order IDs in any spelling, partial customer names, close candidates when nothing matches | `backend/tools.py`, `rules.py`, `discovery.py`, `order_search.py` |
| Morning briefing | Built deterministically; `GET /briefings/latest` serves it live and the scheduler saves a dated copy at 07:00 (`GET /briefings`) | `backend/briefing.py`, `scheduler.py` |
| Multi-turn Q&A | One LangChain agent, 34 tools (including period totals and week-on-week comparisons), SQLite sessions; each answer returns its tool calls, cited source rows and proposals | `backend/llm.py`, `service.py`, `evidence_refs.py` |
| Feasibility estimates | Single- and multi-order scenarios; new plans start on the current data date, while capacity/queue inputs are identified as the original course snapshot. Revisions preserve the original start unless changed explicitly. In-house load is a conservative scenario, not a guaranteed completion bound. Outsourcing reports batch rework probabilities, fixed transport overhead and conditional full-redo dates under stated assumptions; also `POST /feasibility/estimate` | `backend/production_estimates.py`, `production_optimizer.py`, `outsourcing_risk.py`, `views.py` |
| Confirmed actions + audit | Built: the agent or the UI proposes, and only Confirm in the app carries it out; 24 h expiry, confirming twice does nothing more, append-only audit log | `backend/actions.py`, `action_tools.py`; UI `FollowUps.tsx`, `ProposalCard.tsx` |
| Standing watches / alerts | Built: 4 order conditions checked against scripted, versioned data snapshots; one alert per trigger, and only the manager's own watches and reminders alert (see Alerts below). Loading a snapshot moves the whole app to that day (chat, briefing, evidence), with simulated values labelled; reminders keep the real calendar | `backend/watches.py`, `track1/scenarios/watch_snapshots.json`; UI `Watches.tsx` |
| APScheduler | Built: 07:00 briefing, due reminders, watch checks, proposal expiry; restarts do not repeat a run | `backend/scheduler.py` |
| Static Skills | Built: 8 Markdown Skills, each with its tools; `prompt_version` is returned with every answer | `backend/skills/`, `skills.py` |
| Answer check | Heuristic presence check for supported IDs, dates and some numbers, including values in the user's request. It excludes small integers and does not verify entity/value relationships or meaning. Only an answer with unmatched values and no tool call is retried once. The UI explains these limits | `backend/answer_check.py`, `service.py`; UI `Chat.tsx` |
| Voice | Built in the browser, in any language: dictation into the chat box (85 languages and regions; the manager still presses Send) and read-aloud that uses each answer's own language (see Voice below) | `frontend/src/voice.ts`, `useVoice.ts`; UI `Chat.tsx` |
| Web interface | Built: chat with past conversations alongside, briefing with modules that open in place, filterable Orders page (totals from `GET /orders`), Actions and Watches pages that refresh themselves, Ctrl+K search | `frontend/` |
| Evaluation set and runner | 30 evaluation-suite and 17 development cases; four iterative real-model evaluation runs plus one development run on 11 Nov 2026. Historical scores are provisional, not independent held-out results. Reports and failure ledger are retained unchanged | `evaluation/` (see its README) |

## Alerts: what interrupts and what waits

The manager decides what may interrupt. Only a watch or a reminder that the manager asked for and
confirmed raises an alert; everything the system finds on its own waits for the 07:00 briefing,
where it is ranked into *act now* and *watch*.

| Event | Interrupts? | What the manager sees |
|---|---|---|
| A confirmed watch's condition is met | Yes | Alert on the Watches page, counted on the dock badge. Once; the watch then ends (TRIGGERED) |
| A confirmed reminder falls due | Yes | Alert on the Watches page, counted on the Watches and Actions badges. Once |
| A new briefing is saved (07:00, or a new data day) | No | System notice on the Watches page, not counted |
| What the data shows: orders at risk or overdue, stage output drops, customers slipping | No | Next morning briefing, ranked by severity |
| A proposal waits for confirmation | No | Actions badge until confirmed, cancelled or expired (24 h) |
| A watch can no longer fire, a proposal expires, a scheduled job fails | No | Audit log; a failed watch check also shows "Check failed" on the watch |

Why this split:
- **The manager opts in.** A watch is a question the manager asked; answering it is never noise.
  The system's own findings are many and mostly known, so they are batched into one briefing.
- **The data has no live feed.** The course data is a fixed snapshot and the scripted snapshots
  change only orders, so an alert about anything else would repeat the briefing.
- **Each cause alerts once.** Every alert has a unique key (`reminder:<id>`, `watch:<id>`), so a
  repeated check or a restart never repeats it.
- **No outside channel.** Alerts stay in the app; nothing is emailed or messaged.

Not done: severity-based alerts for findings (planned in `docs/TRACK1_IMPLEMENTATION_PLAN.md` 12.4),
and a user setting for alert sensitivity.

## Voice

Voice uses the browser's Web Speech API; the backend never receives audio and nothing is installed.

- **Any language.** The agent already replies in the user's language (`base_grounding_policy`
  Skill), so a question asked in Malay, Tamil or Chinese gets an answer in that language.
- **Speak a question:** the microphone button beside Send fills the chat box as you talk and stops
  after a pause. The text is not sent until you press Send, so a misheard order ID can be fixed
  first. Pick the spoken language under the chat box: 85 languages and regions, named in their own
  language, with the browser's languages first. Speech services cannot guess the language, so it
  has to be picked; it starts as the browser's language.
- **Hear an answer:** *Read aloud* under any answer, or tick *Read answers aloud* to hear each new
  answer. Each answer is read in its own language, whatever the dictation setting: the writing
  system decides first (Chinese, Japanese, Korean, Cyrillic, Arabic, Thai, Indic scripts and
  others), and Latin-alphabet languages are told apart by common words. Where two look alike
  (Malay and Indonesian), the picked language decides. Simplified and Traditional Chinese and
  Cantonese get their own voices. If the device has no voice for that language, the page says so
  instead of reading it with the wrong voice. Markdown symbols are dropped and tables are read row
  by row. Starting the microphone, sending, or leaving the conversation stops the reading.
- **Browsers:** dictation works in Chrome, Edge and Safari; Firefox has read-aloud only, and the
  microphone button is hidden where dictation is missing. Dictated audio goes to the browser
  maker's speech service (Google for Chrome, Microsoft for Edge, Apple for Safari); read-aloud uses
  voices on the device.
- The language choice and the read-aloud switch are kept in this browser only.

## Project Overview

The system combines a general-purpose LLM with deterministic Python tools, static task skills, operational data, application state, and a web interface.

The LLM is responsible for understanding user requests and explaining results. Operational facts, numerical calculations, feasibility checks, and business judgements are handled by deterministic Python tools rather than generated directly by the LLM.

The project focuses on five tool families:

- Retrieval tools
- Judgement tools
- Traceability tools
- Discovery tools
- Action tools

## Project Objectives

The project aims to deliver six core capabilities:

1. Generate a scheduled morning operations briefing.
2. Support multi-turn operational Q&A using the latest available data.
3. Monitor standing watches and raise relevant alerts.
4. Produce feasibility estimates with explicit assumptions.
5. Require user confirmation before executing or recording actions.
6. Trace important claims back to the supporting source rows.

## MVP Architecture

| Component | Technology / Approach |
|---|---|
| Frontend | React + TypeScript |
| Backend | Python + FastAPI + Pydantic |
| Agent | General-purpose LLM + LangChain |
| Tools | Deterministic Python functions |
| Skills | Static task rules and workflows |
| Operational data | Read-only CSV files |
| Application state | SQLite |
| Scheduling | APScheduler |
| Testing | pytest |
| Evaluation | Fixed evaluation dataset + independent evaluation scripts |

The initial MVP uses a single-agent workflow.

The project does not train a model, build custom multi-agent/LangGraph orchestration, discover skills
dynamically, or add a separate vector RAG service. LangChain's agent uses LangGraph internally as
its execution runtime.

## Data

The initial system uses the provided Track 1 datasets:

- `orders.csv`
- `production_log.csv`
- `workshops.csv`

The CSV files are treated as the source of operational facts.

SQLite is used only for application state, including:

- Sessions
- Standing watches
- Notes
- Confirmations
- Actions
- Audit records

## Course Milestones

All times are Singapore Time (SGT).

| Date | Milestone |
|---|---|
| 16 October 2026, 3:00 PM | Sprint 1 submission |
| 16 October 2026, 7:00 PM | Sprint 1 live presentation |
| 30 October 2026, 3:00 PM | Sprint 2 presentation and video submission |
| 13 November 2026, 3:00 PM | Sprint 3 presentation and video submission |
| 15 November 2026, 11:59 PM | Final project submission |
| 25 November 2026, 11:59 PM | Reimbursement submission |

Detailed weekly tasks, deliverables, and acceptance criteria are maintained in the [Track 1 Implementation Plan](./docs/TRACK1_IMPLEMENTATION_PLAN.md).

## Team Responsibilities

Member labels A–F are temporary and will be replaced with the team members' names.

| Member | Primary Responsibility | Main Deliverables |
|---|---|---|
| A | Product, architecture, integration, and evaluation coordination | Project scope, API contract, architecture, sprint coordination, system integration, course requirement checks, and final delivery |
| B | Data, retrieval, and traceability tools | CSV validation, data access layer, retrieval tools, source-row citations, and tool tests |
| C | Judgement, discovery, and feasibility tools | Operational rules, discovery tools, feasibility calculations, assumptions, business logic, and tests |
| D | LLM, LangChain, and static skills | Structured request parsing, agent workflow, clarification and refusal behaviour, faithful explanations, and language evaluation cases |
| E | State, scheduling, watches, and action safety | SQLite state, APScheduler jobs, standing watches, confirmation workflow, action logging, and audit records |
| F | React, UX, demo, and usability | User interface, morning briefing and Q&A views, evidence display, confirmation flow, usability testing, screenshots, and demo video |

Every pull request should be reviewed by at least one other team member.

## Evaluation

The project will be evaluated through:

- Unit tests for deterministic Python tools
- Integration tests for the end-to-end workflow
- At least 30 verified operational questions
- At least 5 ambiguous, unanswerable, or hallucination-bait cases
- At least 5 feasibility or action-safety cases
- Traceability checks from generated claims to source rows
- Individual analysis of at least 10 failure cases
- Usability testing of the complete manager workflow

Evaluation results will be reported by category rather than only as a single overall score.

## Current Progress

- [x] Track 1 selected
- [x] MVP scope and architecture defined
- [x] Initial implementation plan created
- [x] Repository structure and development environment
- [x] Data access layer and deterministic tools (read-only)
- [x] Agent workflow and static skills
- [x] SQLite application state (sessions, follow-ups, watches, alerts, audit)
- [x] Scheduler and standing watches
- [x] React user interface (chat, briefing, orders, actions, watches and alerts)
- [x] End-to-end system integration (merged on `main` in PR #3; real-model smoke test passed 11 Nov 2026)
- [x] Historical real-model development runs (latest stored scores 29/30 and 15/17)
- [ ] Independently reviewed labels and held-out evaluation on the final clean commit
- [ ] Failure analysis write-up and team review of the cases
- [ ] Final documentation and demonstration

## Documentation

- [Sprint 3 Changes](./docs/SPRINT3_CHANGES.md) — data date, outsourcing risk, answer check, evaluation runs, new interface
- [Final fixes](./docs/FINAL_FIXES_2026-11-11.md) — local reliability fixes, validation and remaining release work
- [Sprint 2 Changes](./docs/SPRINT2_CHANGES.md) — everything changed on the integration branch, how it was checked, and what is open
- [Track 1 Implementation Plan](./docs/TRACK1_IMPLEMENTATION_PLAN.md)
- [Backend module map](./backend/README.md) and [Frontend](./frontend/README.md)
- Contribution guidelines — to be added
- API documentation — generated by FastAPI at `/docs` while the backend runs
- [Evaluation](./evaluation/README.md) — case format, running, scoring and its limits; reports go to `evaluation/reports/`

## Repository Workflow

Development follows this workflow:

1. Create or select a GitHub Issue.
2. Create a short-lived branch from the latest `main`.
3. Implement the change and add relevant tests.
4. Open a pull request.
5. Complete peer review and required checks.
6. Merge the pull request into `main`.
7. Delete the merged source branch.

Direct development on `main` should be avoided.

## Definition of Done

A task is considered complete only when it includes:

- Working implementation
- Relevant tests
- Supporting evidence
- Updated documentation
- Reviewer approval

“Works on my computer” alone is not considered complete.
