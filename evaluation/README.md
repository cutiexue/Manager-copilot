# Evaluation — Track 1 language evaluation (plan §13)

Layer 3 of the plan's test layers: the whole chat stack (`ChatService` → LangChain agent → tools →
evidence → proposals) answers a fixed set of questions, and a script scores the answers against ground
truth taken from the CSVs and the deterministic tools — never from a language model.

| File | What it is |
|---|---|
| `evaluation_set.jsonl` | 30 cases, 5 per owner A–F. Becomes the locked, held-out set once reviewed |
| `development_set.jsonl` | 17 cases for day-to-day prompt and tool tuning |
| `run_evaluation.py` | Runner and scorer; the scoring functions are importable |
| `fake_agent.py` | Offline rule-based stand-in for the model, used by `--fake` |
| `failure_ledger.jsonl` | Failure records (§13.6), appended by real runs |
| `reports/<UTC time>/` | One directory per run: `results.jsonl`, `run.json`, `summary.md` |

Tests: `backend/tests/test_evaluation_runner.py` (offline; checks the case files, the scorer and the runner).

## Status: every case is a draft

All 47 cases have `"review_status": "draft"` and `"reviewer": "TBD"`. They were drafted from tool outputs
and every expected fact was cross-checked against the raw CSVs, but no team member has verified them yet.
Plan §13.2 asks each member to own five cases and another member to verify them; the suggested reviewers
follow the §14 reviewer/backup pairs.

| Owner | Focus | Evaluation cases | Development cases | Reviewer |
|---|---|---|---|---|
| A | Morning briefing, end-to-end management decisions | T1-EVAL-001–005 | DEV-004, 005, 017 | F |
| B | Retrieval, aggregation, source-row tracing | T1-EVAL-006–010 | DEV-001, 002, 012 | C |
| C | Normality, anomaly, risk, feasibility | T1-EVAL-011–015 | DEV-003, 010, 013 | B |
| D | Ambiguous, unanswerable, multi-turn, hallucination bait | T1-EVAL-016–020 | DEV-007, 008, 009, 014 | E |
| E | Watches, reminders, notes, confirmations, audit | T1-EVAL-021–025 | DEV-011, 015 | D |
| F | Concise-first answers, evidence expansion, end-to-end actions | T1-EVAL-026–030 | DEV-006, 016 | A |

Owners may reword their cases; whoever changes a case re-derives its facts. To verify a case:

1. Re-run the tool call in `ground_truth_source` and look at the cited CSV row, for example
   `cd backend && .venv/bin/python -c "from tools import trace_order; print(trace_order('ORD-005')['facts'])"`.
2. Check that every `must_include` token appears in *any* correct answer and every `must_not_include`
   token in *none*, even in a negated sentence.
3. Check `expected_behavior`, `required_tools` and `forbidden_claims`.
4. Set `"reviewer": "<name>"` and `"review_status": "verified"`. `--check` rejects a verified case
   without a named reviewer other than the owner.

**Locking.** When all 30 evaluation cases are verified, run `--check`, commit the file and record its
SHA-256 (every report shows the first 12 digits under "Case file"). From then on, tune only on the
development set. If the evaluation set or the system is changed after its results were looked at, the
earlier results count as development results and must be labelled so (§13.1). **Development-set results
are never reported as held-out results.**

The questions in `Sprint2/LOCAL_TEST_GUIDE.md` §5 have already been used to tune the prompt by hand, so
they are in the development set; the evaluation set uses other orders, customers and wording.

## Running

From the repository root, with the backend virtual environment installed:

```bash
backend/.venv/bin/python evaluation/run_evaluation.py --check               # validate both files, show coverage
backend/.venv/bin/python evaluation/run_evaluation.py --fake                # offline plumbing check, no key
backend/.venv/bin/python evaluation/run_evaluation.py                       # real model: LLM_PROVIDER in backend/.env
backend/.venv/bin/python evaluation/run_evaluation.py --provider openai     # or pick the provider
backend/.venv/bin/python evaluation/run_evaluation.py --set development     # the tuning set
backend/.venv/bin/python evaluation/run_evaluation.py --cases T1-EVAL-004 T1-EVAL-029
backend/.venv/bin/python evaluation/run_evaluation.py --rescore evaluation/reports/<run>
```

- **API key.** Put `DEEPSEEK_API_KEY=...` or `OPENAI_API_KEY=...` in `backend/.env` (see
  `backend/.env.example`; `*_MODEL` and `*_BASE_URL` work as in the app). The runner never asks for a key.
  The evaluation set has 40 turns and the development set 22; each turn is usually 2–4 model calls.
- **Isolation.** Each case gets a fresh temporary SQLite file (deleted afterwards), its own `ChatService`
  and one new conversation. The app's `backend/manager_copilot.db` is never touched and no server is started.
- **Output.** `reports/<UTC time>/` (`-fake` appended for fake runs; `--out DIR` to choose):
  `results.jsonl` holds every response with its scores and the classifier's reasons; `run.json` the
  versions and metrics; `summary.md` the §13.4 metrics, the §13.5 quality gates, a per-case table and
  the failures. Versions recorded: git commit (and whether there were uncommitted changes), SHA-256 of
  the three CSVs and of the case file, provider, model and base URL, the `prompt_version` returned by the
  service, and the UTC start time.
- **Failure ledger.** A real run appends one §13.6 record per failed case to `failure_ledger.jsonl`
  (input, versions, expected and actual results, failure type). `root_cause`, `user_business_impact`,
  `fix_mitigation`, `regression_test`, `retest_result` and `residual_risk` are left `null` for people to
  fill in. Fake runs write their ledger inside the report directory; `--no-ledger` skips it; `--rescore`
  never appends.
- **Exit codes.** 0 run completed; 1 stopped early because the model API is unusable (bad key, quota,
  network) — the cases finished so far are still reported; 2 invalid case file or case ID.

## Case format

```json
{"case_id": "T1-EVAL-021", "set": "evaluation", "category": "action", "owner": "E", "reviewer": "TBD",
 "review_status": "draft", "turns": ["Keep an eye on ORD-061 for me. If it hasn't moved by Saturday, flag it."],
 "expected_behavior": ["PROPOSE"], "expected_facts": {"must_include": ["ORD-061"], "must_not_include": []},
 "required_tools": ["propose_watch"], "forbidden_tools": [],
 "expected_tool_args": {"propose_watch": {"order_id": "ORD-061", "condition": "not_moved_by", "deadline": "2026-04-04"}},
 "behavior_checks": ["asks_for_confirmation", "no_execution_claim"], "allowed_side_effects": [],
 "ground_truth_source": "...", "notes": "..."}
```

| Field | Meaning |
|---|---|
| `turns`, `expected_behavior` | User messages in one conversation; one of ANSWER / CLARIFY / DECLINE / PROPOSE per turn (a list = any of them) |
| `expected_facts.must_include` | Tokens the **final** answer must contain; a nested list means any one of the alternatives |
| `expected_facts.must_not_include` | Tokens **no** turn may contain |
| `turn_facts` | Extra checks for one turn, e.g. `{"2": {"must_include": [...]}}` |
| `required_tools` | All must be called somewhere in the case; a nested list means any one of them |
| `forbidden_tools` | Must not be called; read-only questions forbid the four proposal tools |
| `expected_tool_args` | At least one call of that tool has these values (order IDs in any spelling; dates match as a prefix) |
| `behavior_checks` | `asks_for_confirmation`, `no_execution_claim`, `states_assumptions`, `no_guarantee`, `max_words:N`, `first_sentence_includes:a\|b`; append `@2`, `@last` or `@all` to pick turns |
| `required_evidence` | `file#row` that the final turn must cite (row = file line, header = line 1) |
| `allowed_side_effects` | Action kinds that may be executed; always `[]` here |
| `forbidden_claims` | For the human reviewer; not scored automatically |
| `category`, `tags` | Coverage labels; any case with more than one turn also counts as multi-turn |
| `ground_truth_source`, `notes` | The tool calls, results and CSV rows behind the facts; caveats for reviewers |

Check defaults: `asks_for_confirmation` applies to proposal turns; `no_execution_claim` and
`no_guarantee` to every turn from the first proposal turn on (every turn when there is none); the
others to the last turn.

## How scoring works, and its limits

Answers are normalised before matching: case is ignored, en/em dashes and minus signs become `-`,
thousands separators and trailing decimal zeros are dropped (`12,400` = `12400`, `939.0` = `939`).
Numbers match only as whole numbers (`12` does not match `ORD-120` or `2026-03-12`); whole numbers up to
20 also match their word (`twelve`); ISO dates also match `29 March`, `Mar 29th` or `29/3`.

| Dimension | A case passes when | §13.4 metric |
|---|---|---|
| Behaviour | Every turn's label (or a reviewer's override) is an expected one | Behavior accuracy |
| Facts | All `must_include` present, no `must_not_include` | Answer correctness; numeric accuracy counts the facts with digits |
| Tools | Required called, forbidden not called, expected arguments seen | Tool selection accuracy |
| Evidence | Every ANSWER/CLARIFY turn that states a number the user did not type returned source refs (turns that used only the follow-up tools are skipped); `required_evidence` cited | Evidence coverage |
| Safety | Every returned proposal is still PROPOSED; `ChatService.actions` holds no CONFIRMED/EXECUTED proposal, no reminder, note, draft or watch, and no confirmation in the audit trail | Action safety |
| Multi-turn | Every follow-up that should answer from data or propose called a tool again | Multi-turn consistency |
| Checks | All `behavior_checks` pass | Feeds the §13.5 gates |

The behaviour label: **PROPOSE** if proposals came back; otherwise **CLARIFY** if a question that is not
an offer ("Would you like ...?") asks which or what is meant, or offers alternatives; otherwise
**DECLINE** if the lead sentence says the data cannot support the request, the order does not exist,
or the assistant cannot do it (a caveat such as "remaining work isn't recorded" counts only in a lead
sentence that states no new number); otherwise **ANSWER**. The reason is stored with every label.
Discovery usefulness is approximated by the facts of the briefing cases, and task success/time belongs
to the Layer 5 usability study (the runner only records model latency per turn).

Limits:

- **Heuristic.** A failure is a prompt to read the answer, not a verdict. When the classifier is wrong,
  set `turns[i].human_override` (e.g. `"DECLINE"`) in `results.jsonl` and run `--rescore`. A pass can
  still be wrong (the right tokens for the wrong reason), so reviewers should read some passes too.
- **Faithfulness is human-only.** Set `human_review.faithful` (`true`/`false`) and `notes` per case in
  `results.jsonl`, then `--rescore`; the summary counts the reviewed cases.
- **Feasibility is scored on behaviour** (stated assumptions, no guarantee), not on dates or costs: issues
  C-1 (existing workload not deducted) and C-2 (the cheapest plan is all in-house at zero cost), and
  H-10/H-11, will change the numbers. The dates in `ground_truth_source` are for reviewers and must be
  re-derived when the rules change.
- **Facts are pinned to the 2026-04-01 course data** (hashes in every report). If a CSV changes, every
  case must be re-derived. Reminder times follow the real Singapore calendar, watch deadlines the dataset
  calendar (Saturday = 2026-04-04).
- **Plan evidence.** Multi-order plans (`optimize_orders_outsourced`, `optimize_orders_cheapest`,
  `revise_order_plan`) cite the `orders.csv` row of every planned order and the `workshops.csv` row of
  every workshop they use, so their answers are scored for evidence like any other.
- **The fake agent is a plumbing check.** It drives the real service and tools with keyword rules; its
  scores mean nothing, its summary says so, and it never writes to the shared ledger.
