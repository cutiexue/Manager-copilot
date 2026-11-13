# Q14: report Pass → retest Partial

**Prompt (Evaluation.pdf Appendix A):** Give me the five most important things to focus on today, with evidence and any decisions I need to make.

**Report verdict:** Pass (evidence M09)

**Report expected:** Five evidence-led priorities, explicit decisions, uncertainty and current follow-ups.

**Report observed:** Five priorities with decisions and sources; prior count/causal overstatement not repeated. Auxiliary reminder date flagged, not independently verified against SQLite.

**Retest verdict (main run):** Partial. Five priorities and decisions are correct, but item 3 states "yesterday 455 vs 939-avg baseline": 939 is the KNITTING 7-day baseline (get_morning_briefing yesterday.stages[0]); the Assembly baseline is 515.7.

**Stability:** 3 runs → Partial, Pass, Pass. Runs 2 and 3 give correct figures (Assembly 432 vs 611, -29.3%; yesterday 455, -11.8% vs its own 7-workday average). The 939 misattribution appeared in 1 of 3 runs.

**Files:** `main_run/` holds the full record (JSON: every request, answer, tool call with arguments and results, evidence rows, answer check, proposals, clicks and state reads) and a readable transcript (.md); `rerun2/` and `rerun3/` hold the repeat runs.

Model deepseek/deepseek-flash; prompt version f9348b4de425; code 290e5f7 plus the uncommitted changes in `../../../code_version/uncommitted.patch` (the code includes the post-evaluation fixes for F04, F11, F12 and F13).
