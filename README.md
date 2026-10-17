# Manager Co-Pilot

DSS5105 Capstone Project — **Track 1: The General Manager's Co-Pilot**

Manager Co-Pilot is an AI-assisted decision-support system for factory general managers. It helps users understand current operations, identify risks, estimate feasibility, and take controlled actions based on traceable production data.

> **Current phase:** Sprint 2 — read-only tools, chat API and UI shell are integrated; action, watch and scheduler layers are not built yet (see [Implementation Status](#implementation-status)).

## Quick Start

Requires Python 3.12 and Node.js 18+.

```text
Manager-copilot/
├── backend/                 # FastAPI + LangChain agent + deterministic tools (flat modules)
│   ├── track1/data/         # read-only course CSVs (orders, production_log, workshops)
│   └── tests/               # pytest suite, no API key needed
├── frontend/                # React + TypeScript + Vite
└── TRACK1_IMPLEMENTATION_PLAN.md
```

Backend and tests:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest          # deterministic tools, SQLite store, chat API with a fake agent
python main.py --local    # one order lookup, no LLM call
python main.py --api      # asks for provider + API key, serves 127.0.0.1:8000
```

Frontend (second terminal):

```bash
cd frontend
npm install
npm run dev               # http://localhost:5173, proxies /api/* to the backend
```

Chat sessions are stored in `backend/manager_copilot.db` (SQLite, git-ignored). Copy `backend/.env.example` to `backend/.env` for local settings; never commit `.env`.

## Implementation Status

| Workflow / layer | Status | Where |
|---|---|---|
| Retrieval, judgement, tracing, discovery tools | Built, read-only, tested | `backend/tools.py`, `rules.py`, `discovery.py` |
| Morning briefing content | Built deterministically; no scheduler, no API endpoint | `backend/briefing.py`; UI reads `frontend/src/fixtures/briefing.json` |
| Multi-turn Q&A | Built: one LangChain agent, 21 tools, SQLite sessions | `backend/llm.py`, `service.py`, `api.py`, `storage.py` |
| Feasibility estimates | Built (in-house, per-workshop, fastest/cheapest plan) | `backend/production_estimates.py`, `production_optimizer.py` |
| Standing watches / alerts | Not started | — |
| Confirmed actions + audit | UI demo only (browser state); no backend | `frontend/src/components/ConfirmModal.tsx` |
| APScheduler | Not started | — |
| Static Skills files | Not started; rules live in one system prompt | `backend/llm.py` |
| Evaluation set and runner | Not started | — |

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
- [ ] Agent workflow and static skills (agent done; skills not split out)
- [ ] SQLite application state (chat sessions only; watches, actions, audit missing)
- [ ] Scheduler and standing watches
- [ ] React user interface (shell done; briefing is a snapshot, actions are browser-only)
- [ ] End-to-end system integration
- [ ] Evaluation and failure analysis
- [ ] Final documentation and demonstration

## Documentation

- [Track 1 Implementation Plan](./TRACK1_IMPLEMENTATION_PLAN.md)
- Contribution guidelines — to be added
- API documentation — to be added
- Evaluation report — to be added

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
