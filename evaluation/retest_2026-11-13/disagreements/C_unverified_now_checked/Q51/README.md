# Q51: report Unverified → retest Pass

**Prompt (Evaluation.pdf Appendix A):** Remind me to follow up on ORD-002 at 15:00 on 12 November 2026.

**Report verdict:** Unverified (evidence M32)

**Report expected:** Confirm ORD-002 reminder for November 12 at 15:00; no early alert and exactly one on/after due time.

**Report observed:** Card shows saved at intended time. No scheduler trace; isolated direct firing test passed at a different fixed date.

**Retest verdict (main run):** Pass. Clock 12 Nov 10:00: proposal for 12 Nov 15:00, confirmed; no alert at 14:59, one at 15:00, none at 15:01.

**Files:** `main_run/` holds the full record (JSON: every request, answer, tool call with arguments and results, evidence rows, answer check, proposals, clicks and state reads) and a readable transcript (.md).

Model deepseek/deepseek-flash; prompt version f9348b4de425; code 290e5f7 plus the uncommitted changes in `../../../code_version/uncommitted.patch` (the code includes the post-evaluation fixes for F04, F11, F12 and F13).
