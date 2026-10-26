# Manager Co-Pilot

DSS5105 Capstone Project — **Track 1: The General Manager's Co-Pilot**

Manager Co-Pilot is an AI-assisted decision-support system for factory general managers. It helps users understand current operations, identify risks, estimate feasibility, and take controlled actions based on traceable production data.

> **Current phase:** Sprint 2 — read-only tools, chat with evidence, confirmed follow-ups (reminders, notes, chase-up drafts, watches), the scheduler and static Skills are integrated on the local integration branch; the evaluation set is a draft for team review (see [Implementation Status](#implementation-status)).

## Quick Start

Requires Python 3.12 and Node.js 18+.

```text
Manager-copilot/
├── backend/                 # FastAPI + LangChain agent + deterministic tools (flat modules)
│   ├── skills/              # static Skills (Markdown), composed into the system prompt
│   ├── track1/data/         # read-only course CSVs (orders, production_log, workshops)
│   ├── track1/scenarios/    # scripted, versioned data snapshots for standing watches
│   └── tests/               # pytest suite, no API key needed
├── evaluation/              # question sets and the evaluation runner
├── frontend/                # React + TypeScript + Vite
└── TRACK1_IMPLEMENTATION_PLAN.md
```

Backend and tests:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest          # tools, SQLite store, chat + briefing API with a fake agent
python main.py --local    # one order lookup, no LLM call
python main.py            # terminal menu: conversations, history, on-demand briefing
python main.py --api      # serves 127.0.0.1:8000 for the frontend and starts the scheduler
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
| Multi-turn Q&A | One LangChain agent, 32 tools, SQLite sessions; each answer returns its tool calls, cited source rows and proposals | `backend/llm.py`, `service.py`, `evidence_refs.py` |
| Feasibility estimates | Single batch (in-house, per workshop, fastest/cheapest) and multi-order plans with revision; in-house work queues behind the unfinished orders (an upper bound), and the cheapest plan leaves in-house out unless its cost is given; also `POST /feasibility/estimate` | `backend/production_estimates.py`, `production_optimizer.py`, `views.py` |
| Confirmed actions + audit | Built: the agent or the UI proposes, and only Confirm in the app carries it out; 24 h expiry, confirming twice does nothing more, append-only audit log | `backend/actions.py`, `action_tools.py`; UI `FollowUps.tsx`, `ProposalCard.tsx` |
| Standing watches / alerts | Built: 4 order conditions checked against scripted, versioned data snapshots; one alert per trigger | `backend/watches.py`, `track1/scenarios/watch_snapshots.json`; UI `Watches.tsx` |
| APScheduler | Built: 07:00 briefing, due reminders, watch checks, proposal expiry; restarts do not repeat a run | `backend/scheduler.py` |
| Static Skills | Built: 8 Markdown Skills, each with its tools; `prompt_version` is returned with every answer | `backend/skills/`, `skills.py` |
| Evaluation set and runner | Draft: 30 held-out and 17 development cases, every fact rechecked against the CSVs; not yet reviewed by a second member; offline plumbing run passes, first real-model run pending an API key | `evaluation/` (see its README) |

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

Model training, LangGraph, multi-agent orchestration, dynamic skill discovery, and a separate RAG system are outside the initial scope unless later evidence shows they are necessary.

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

Detailed weekly tasks, deliverables, and acceptance criteria are maintained in the [Track 1 Implementation Plan](./TRACK1_IMPLEMENTATION_PLAN.md).

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
- [ ] End-to-end system integration (local integration branch, not pushed; first run with a real model pending)
- [ ] Evaluation and failure analysis (draft cases and runner ready; team review and the first real-model run pending)
- [ ] Final documentation and demonstration

## Documentation

- [Track 1 Implementation Plan](./TRACK1_IMPLEMENTATION_PLAN.md)
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
