# Backend

FastAPI + one LangChain agent over deterministic Python tools. The modules are kept flat (every
import is `from rules import ...`), so they are grouped here by layer instead of by folder.
A module only imports from its own layer or the layers above it in this list.

| Layer | Modules | What they do |
|---|---|---|
| Files and rules | `paths.py`, `data_loader.py`, `rules.py` | Where every file lives; loading and validating the course CSVs (plus scripted snapshot changes); the operational rules (overdue, idle, at risk) and the current data date |
| Read-only tools | `tools.py`, `discovery.py`, `order_search.py`, `period_output.py`, `evidence_refs.py` | Order, customer and stage lookups; findings nobody asked about; order search and the Orders page list; period totals; the source rows behind every result |
| Planning | `production_estimates.py`, `production_optimizer.py`, `outsourcing_risk.py`, `plan_context.py` | Feasibility of assigned batches, fastest and cheapest plans, outsourcing risk from `workshops.csv`, revising the last plan in a conversation |
| Briefing and watches | `briefing.py`, `watches.py`, `scheduler.py` | The morning briefing; standing watches checked against `track1/scenarios/`; the 07:00 job, reminders, watch checks |
| Follow-ups and state | `actions.py`, `action_tools.py`, `storage.py` | Proposals that only Confirm carries out, reminders, notes, drafts, alerts, the audit log; conversation history (SQLite) |
| Agent | `skills.py` + `skills/`, `tool_schemas.py`, `llm.py`, `order_selection.py`, `answer_check.py`, `service.py` | Skills composed into the prompt; the 34 tool schemas; the agent; "these orders" across turns; checking each answer's figures against the tool results; the one service both the CLI and the API call |
| Entry points | `main.py`, `api.py`, `views.py`, `config.py`, `demo_backend.py` | CLI and `--api` server; HTTP routes; read-only views for the UI; model settings from `.env`; the same API with a keyword demo model (no API key) |

Data: `track1/data/` holds the course CSVs and their data dictionary (read-only, never edited);
`track1/scenarios/watch_snapshots.json` holds the scripted later days used for watches and demos.

Tests: `python -m pytest` from this folder (no API key needed). Each test file is named after the
module or workflow it covers.
