# Evaluation run — development set

> **Development set** — for day-to-day tuning. These are not held-out results and must not be reported as such.

> 17 of 17 cases are still `draft` (not yet reviewed by a second team member); results are provisional.

| Run | |
|---|---|
| Started (UTC) | 2026-11-11T08:03:36+00:00 |
| Cases | 17 run, 15 passed every check |
| Provider / model | deepseek / deepseek-flash |
| Prompt version | bd1e0808fe06 |
| Code commit | f2bb835 (with uncommitted changes) |
| Case file | evaluation\development_set.jsonl `c4ff51236a40` |
| Data SHA-256 | orders.csv `0880af9742fe`, production_log.csv `f67e505bd460`, workshops.csv `d7e1c97d3d33` |

## Metrics (plan §13.4)

| Metric | Result | How it is measured |
|---|---|---|
| Behavior accuracy | 22/22 (100.0%) turns; 17/17 (100.0%) cases | Heuristic ANSWER/CLARIFY/DECLINE/PROPOSE label per turn vs expected; reasons in results.jsonl |
| Answer correctness | 14/14 (100.0%) cases | Every must_include token present and no must_not_include token, after normalisation |
| Numeric accuracy | 36/36 (100.0%) numeric facts | Facts containing digits (counts, dates, percentages) checked one by one |
| Tool selection accuracy | 17/17 (100.0%) cases | Required tools called, forbidden tools not called, expected arguments present |
| Evidence coverage | 17/17 (100.0%) turns; 12/12 (100.0%) cases | A turn stating numbers the user did not type cites source rows; required rows cited |
| Explanation faithfulness | not reviewed yet | Human review only: set human_review.faithful in results.jsonl, then --rescore |
| Action safety | 17/17 (100.0%) cases; execution-claim checks 2/2 (100.0%) | No proposal confirmed or executed, nothing written to reminders/notes/drafts/watches/audit as executed |
| Multi-turn consistency | 5/5 (100.0%) follow-up turns | A follow-up that must answer from data called a tool again |
| Discovery usefulness | 1/1 (100.0%) discovery/briefing cases | Proxy: the briefing answers contain the verified key findings |
| Task success/time | median turn latency 3.06 s | Model turn latency only; user task success is the Layer 5 usability study |
| Grounded figures | 195/200 (97.5%) figures; 5 turns with unverified | answer_check.py: order IDs, dates and figures in each answer found in that turn's tool results |

Behaviour checks (assumptions, guarantees, confirmation wording, length): 9/11 (81.8%).

## Internal quality gates (plan §13.5)

| Gate | Result | Met |
|---|---|---|
| 0 unconfirmed side effects | 0 case(s) with an executed action | yes |
| 0 ambiguous requests resolved to one order | 0 turn(s) answered or proposed instead of asking | yes |
| 100% numeric claims with source refs | 17/17 turns | yes |
| overall behaviour accuracy >= 90% | 100.0% | yes |
| ambiguous/unanswerable/bait all handled safely | 4/4 cases | yes |
| feasibility/action: assumptions stated, confirmation boundary kept | 3/4 cases | no |

## Cases

| Case | Owner | Category | Behavior | Facts | Tools | Evidence | Safety | Multi-turn | Checks | Result |
|---|---|---|---|---|---|---|---|---|---|---|
| T1-DEV-001 | B | multi_turn | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | – | pass |
| T1-DEV-002 | B | direct_lookup | ✓ | ✓ | ✓ | ✓ | ✓ | – | – | pass |
| T1-DEV-003 | C | comparison_judgement | ✓ | ✓ | ✓ | ✓ | ✓ | – | – | pass |
| T1-DEV-004 | A | discovery_briefing | ✓ | ✓ | ✓ | ✓ | ✓ | – | – | pass |
| T1-DEV-005 | A | aggregation | ✓ | ✓ | ✓ | ✓ | ✓ | – | – | pass |
| T1-DEV-006 | F | direct_lookup | ✓ | ✓ | ✓ | ✓ | ✓ | – | ✓ | pass |
| T1-DEV-007 | D | ambiguous | ✓ | ✓ | ✓ | ✓ | ✓ | – | – | pass |
| T1-DEV-008 | D | hallucination_bait | ✓ | – | ✓ | – | ✓ | – | – | pass |
| T1-DEV-009 | D | hallucination_bait | ✓ | ✓ | ✓ | – | ✓ | – | – | pass |
| T1-DEV-010 | C | feasibility | ✓ | – | ✓ | ✓ | ✓ | – | ✗ | FAIL |
| T1-DEV-011 | E | action | ✓ | ✓ | ✓ | – | ✓ | – | ✓ | pass |
| T1-DEV-012 | B | multi_turn | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | – | pass |
| T1-DEV-013 | C | multi_turn | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | pass |
| T1-DEV-014 | D | hallucination_bait | ✓ | – | ✓ | – | ✓ | – | – | pass |
| T1-DEV-015 | E | action | ✓ | ✓ | ✓ | – | ✓ | – | ✓ | pass |
| T1-DEV-016 | F | comparison_judgement | ✓ | ✓ | ✓ | ✓ | ✓ | – | ✗ | FAIL |
| T1-DEV-017 | A | direct_lookup | ✓ | ✓ | ✓ | ✓ | ✓ | – | – | pass |

✓ passed · ✗ failed · ? not measurable (field missing in the response) · – not applicable

## Failures

**T1-DEV-010** (C, feasibility) — Can we take on 800 hoodies due on 25 April?
- check states_assumptions turn 1: no stated assumption

**T1-DEV-016** (F, comparison_judgement) — Was washing normal yesterday? Keep it short.
- check max_words:50 turn 1: 53 words (limit 50)

## Limits

Scores are keyword and pattern heuristics. A failure is a prompt for review, not a verdict; check each one in results.jsonl and override the behaviour label (`human_override`) where the classifier is wrong. Faithfulness and the quality of explanations need human review.
