# Q20: report Partial → retest Pass

**Prompt (Evaluation.pdf Appendix A):** Can that order be delivered by the 25th?

**Report verdict:** Partial (evidence M15)

**Report expected:** Resolve order and exact deadline; avoid a promise from missing remaining quantity.

**Report observed:** Asks for order and uses April 25 only conditionally in the conversation. No completion guarantee; confirmation of month is still needed if not established in context.

**Retest verdict (main run):** Pass. Asks which order is meant; no promise made.

**Stability:** 3 runs → Pass, Pass, Pass. All 3 runs ask which order is meant.

**Files:** `main_run/` holds the full record (JSON: every request, answer, tool call with arguments and results, evidence rows, answer check, proposals, clicks and state reads) and a readable transcript (.md); `rerun2/` and `rerun3/` hold the repeat runs.

Model deepseek/deepseek-flash; prompt version f9348b4de425; code 290e5f7 plus the uncommitted changes in `../../../code_version/uncommitted.patch` (the code includes the post-evaluation fixes for F04, F11, F12 and F13).
