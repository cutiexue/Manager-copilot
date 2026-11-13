# Q52: report Unverified → retest Pass

**Prompt (Evaluation.pdf Appendix A):** Watch ORD-002 for no update by 2 April 2026, using the dataset scenario calendar.

**Report verdict:** Unverified (evidence M33)

**Report expected:** Confirmed ORD-002 watch triggers once at scenario deadline if unchanged.

**Report observed:** Watching shown, no alert in screenshot. Separate snapshot component check passed.

**Retest verdict (main run):** Pass. Watch triggers once on the 2 April snapshot; a second check adds no alert.

**Files:** `main_run/` holds the full record (JSON: every request, answer, tool call with arguments and results, evidence rows, answer check, proposals, clicks and state reads) and a readable transcript (.md).

Model deepseek/deepseek-flash; prompt version f9348b4de425; code 290e5f7 plus the uncommitted changes in `../../../code_version/uncommitted.patch` (the code includes the post-evaluation fixes for F04, F11, F12 and F13).
