# Q60: report Partial → retest Pass

**Prompt (Evaluation.pdf Appendix A):** Pull up the Northwind Apparel order and tell me whether it needs chasing.

**Report verdict:** Partial (evidence H04)

**Report expected:** (see report text)

**Report observed:** The assistant lists five unfinished Northwind orders and asks which one is intended, satisfying clarification. However, it says ORD-107 is 9 days overdue. March 16 to April 1 is 16 days; ORD-114 is 9 days overdue. This is a confirmed numeric attribution error. Generate each overdue value from its own order record and preserve this original result if later corrected.

**Retest verdict (main run):** Pass. Five Northwind orders listed; ORD-107 16 days and ORD-114 9 days overdue (fix for F13).

**Stability:** 3 runs → Pass, Pass, Pass. All 3 runs give ORD-107 16 and ORD-114 9 days overdue.

**Files:** `main_run/` holds the full record (JSON: every request, answer, tool call with arguments and results, evidence rows, answer check, proposals, clicks and state reads) and a readable transcript (.md); `rerun2/` and `rerun3/` hold the repeat runs.

Model deepseek/deepseek-flash; prompt version f9348b4de425; code 290e5f7 plus the uncommitted changes in `../../../code_version/uncommitted.patch` (the code includes the post-evaluation fixes for F04, F11, F12 and F13).
