# Q42: report Partial → retest Pass

**Prompt (Evaluation.pdf Appendix A):** Which customers have at least two unfinished overdue orders? State the number of customers first, then list all matching orders by customer.

**Report verdict:** Partial (evidence M26)

**Report expected:** State four customers first, then all eight orders grouped consistently.

**Report observed:** Starts with three and adds Maple at the end, revising to four. Correct final set, inconsistent response.

**Retest verdict (main run):** Pass. States 4 customers first and lists 8 orders grouped by customer, consistently (fix for F04).

**Stability:** 3 runs → Pass, Pass, Pass. All 3 runs state four customers first and list the eight orders consistently.

**Files:** `main_run/` holds the full record (JSON: every request, answer, tool call with arguments and results, evidence rows, answer check, proposals, clicks and state reads) and a readable transcript (.md); `rerun2/` and `rerun3/` hold the repeat runs.

Model deepseek/deepseek-flash; prompt version f9348b4de425; code 290e5f7 plus the uncommitted changes in `../../../code_version/uncommitted.patch` (the code includes the post-evaluation fixes for F04, F11, F12 and F13).
