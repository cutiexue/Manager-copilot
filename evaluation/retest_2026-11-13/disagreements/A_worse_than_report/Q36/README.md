# Q36: report Pass → retest Partial

**Prompt (Evaluation.pdf Appendix A):** Remind me to follow up on O1 at 3 pm on 2 April 2026.

**Report verdict:** Pass (evidence M22)

**Report expected:** Reject past April 2 at 15:00 on real Singapore clock; clarify O1.

**Report observed:** Both boundaries surfaced; separate controlled reminder firing check passed.

**Retest verdict (main run):** Partial. Clarifies O1 but does not say that 2 April 2026 15:00 has already passed; it offers to set the reminder for that past time. The tool rejected the unknown order before checking the time.

**Stability:** 3 runs → Partial, Partial, Partial. Runs 2 and 3 repeat it: both clarify O1 and promise to set the reminder for 2 April 2026 15:00 once the order is known, without noting that time has passed. 3 of 3 runs.

**Files:** `main_run/` holds the full record (JSON: every request, answer, tool call with arguments and results, evidence rows, answer check, proposals, clicks and state reads) and a readable transcript (.md); `rerun2/` and `rerun3/` hold the repeat runs.

Model deepseek/deepseek-flash; prompt version f9348b4de425; code 290e5f7 plus the uncommitted changes in `../../../code_version/uncommitted.patch` (the code includes the post-evaluation fixes for F04, F11, F12 and F13).
