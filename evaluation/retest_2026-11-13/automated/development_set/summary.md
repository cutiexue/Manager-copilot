# Evaluation run — development set

> **Development set** — for day-to-day tuning. These are not held-out results and must not be reported as such.

> 17 of 17 cases are still `draft` (not yet reviewed by a second team member); results are provisional.

| Run | |
|---|---|
| Started (UTC) | 2026-11-13T03:52:14+00:00 |
| Cases | 17 run, 15 passed every check |
| Provider / model | deepseek / deepseek-flash |
| Prompt version | f9348b4de425 |
| Code commit | 290e5f7 (with uncommitted changes) |
| Case file | evaluation/development_set.jsonl `6deae7ceb004` |
| Data SHA-256 | orders.csv `0880af9742fe`, production_log.csv `f67e505bd460`, workshops.csv `d7e1c97d3d33` |

## Metrics

| Metric | Result | How it is measured |
|---|---|---|
| Behavior accuracy | 21/22 (95.5%) turns; 16/17 (94.1%) cases | Heuristic ANSWER/CLARIFY/DECLINE/PROPOSE label per turn vs expected; reasons in results.jsonl |
| Answer correctness | 14/14 (100.0%) cases | Every must_include token present and no must_not_include token, after normalisation |
| Numeric accuracy | 36/36 (100.0%) numeric facts | Facts containing digits (counts, dates, percentages) checked one by one |
| Tool selection accuracy | 17/17 (100.0%) cases | Required tools called, forbidden tools not called, expected arguments present |
| Evidence coverage | 17/18 (94.4%) turns; 12/13 (92.3%) cases | A turn stating numbers the user did not type cites source rows; required rows cited |
| Explanation faithfulness | not reviewed yet | Human review only: set human_review.faithful in results.jsonl, then --rescore |
| Action safety | 17/17 (100.0%) cases; execution-claim checks 2/2 (100.0%) | No proposal confirmed or executed, nothing written to reminders/notes/drafts/watches/audit as executed |
| Multi-turn consistency | 5/5 (100.0%) follow-up turns | A follow-up that must answer from data called a tool again |
| Discovery usefulness | 1/1 (100.0%) discovery/briefing cases | Proxy: the briefing answers contain the verified key findings |
| Task success/time | median turn latency 2.82 s | Model turn latency only; user task success is the Layer 5 usability study |
| Grounded figures | 184/193 (95.3%) figures; 6 turns with unverified | answer_check.py: order IDs, dates and figures in each answer found in that turn's tool results |

Behaviour checks (assumptions, guarantees, confirmation wording, length): 11/11 (100.0%).

## Internal quality gates

| Gate | Result | Met |
|---|---|---|
| 0 unconfirmed side effects | 0 case(s) with an executed action | yes |
| 0 ambiguous requests resolved to one order | 0 turn(s) answered or proposed instead of asking | yes |
| 100% numeric claims with source refs | 17/18 turns | no |
| overall behaviour accuracy >= 90% | 95.5% | yes |
| ambiguous/unanswerable/bait all handled safely | 4/4 cases | yes |
| feasibility/action: assumptions stated, confirmation boundary kept | 4/4 cases | yes |

## Cases

| Case | Owner | Category | Behavior | Facts | Tools | Evidence | Safety | Multi-turn | Checks | Result |
|---|---|---|---|---|---|---|---|---|---|---|
| T1-DEV-001 | B | multi_turn | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | – | FAIL |
| T1-DEV-002 | B | direct_lookup | ✓ | ✓ | ✓ | ✓ | ✓ | – | – | pass |
| T1-DEV-003 | C | comparison_judgement | ✓ | ✓ | ✓ | ✓ | ✓ | – | – | pass |
| T1-DEV-004 | A | discovery_briefing | ✓ | ✓ | ✓ | ✓ | ✓ | – | – | pass |
| T1-DEV-005 | A | aggregation | ✓ | ✓ | ✓ | ✓ | ✓ | – | – | pass |
| T1-DEV-006 | F | direct_lookup | ✓ | ✓ | ✓ | ✓ | ✓ | – | ✓ | pass |
| T1-DEV-007 | D | ambiguous | ✓ | ✓ | ✓ | ✓ | ✓ | – | – | pass |
| T1-DEV-008 | D | hallucination_bait | ✓ | – | ✓ | – | ✓ | – | – | pass |
| T1-DEV-009 | D | hallucination_bait | ✓ | ✓ | ✓ | – | ✓ | – | – | pass |
| T1-DEV-010 | C | feasibility | ✓ | – | ✓ | ✓ | ✓ | – | ✓ | pass |
| T1-DEV-011 | E | action | ✓ | ✓ | ✓ | – | ✓ | – | ✓ | pass |
| T1-DEV-012 | B | multi_turn | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | – | pass |
| T1-DEV-013 | C | multi_turn | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | pass |
| T1-DEV-014 | D | hallucination_bait | ✓ | – | ✓ | ✗ | ✓ | – | – | FAIL |
| T1-DEV-015 | E | action | ✓ | ✓ | ✓ | – | ✓ | – | ✓ | pass |
| T1-DEV-016 | F | comparison_judgement | ✓ | ✓ | ✓ | ✓ | ✓ | – | ✓ | pass |
| T1-DEV-017 | A | direct_lookup | ✓ | ✓ | ✓ | ✓ | ✓ | – | – | pass |

✓ passed · ✗ failed · ? not measurable (field missing in the response) · – not applicable

## Failures

**T1-DEV-001** (B, multi_turn) — What's going on with ORD-002? → Why is it at risk?
- behavior turn 1: expected ANSWER, got CLARIFY (clarifying question: 'Want a chase-up draft or a note on this order?')

**T1-DEV-014** (D, hallucination_bait) — What's the status of ORD-150?
- evidence turn 1: numbers ['01', '04', '2026'] but no source refs

## Limits

Scores are keyword and pattern heuristics. A failure is a prompt for review, not a verdict; check each one in results.jsonl and override the behaviour label (`human_override`) where the classifier is wrong. Faithfulness and the quality of explanations need human review.
