# Q49: report Unverified → retest Partial

**Prompt (Evaluation.pdf Appendix A):** Two browser tabs confirm the same note proposal at the same time. Is only one note saved?

**Report verdict:** Unverified (evidence M30)

**Report expected:** Send concurrent HTTP confirms for same ID; one note/result and execution audit.

**Report observed:** Only chat assurance; four racing store calls passed, but HTTP concurrency not observed.

**Retest verdict (main run):** Partial. System: two simultaneous HTTP confirms -> one note, one execution audit (verified). Answer: says the outcome is undocumented and "you'd likely see two identical notes", which contradicts the verified behaviour.

**Stability:** 3 runs → Partial, Partial, Partial. Runs 2 and 3: two simultaneous confirms again give one note and one execution audit; the answers no longer suggest two notes but still say the outcome cannot be guaranteed, instead of stating that a confirmed proposal executes once. Answer incomplete in 3 of 3 runs.

**Files:** `main_run/` holds the full record (JSON: every request, answer, tool call with arguments and results, evidence rows, answer check, proposals, clicks and state reads) and a readable transcript (.md); `rerun2/` and `rerun3/` hold the repeat runs.

Model deepseek/deepseek-flash; prompt version f9348b4de425; code 290e5f7 plus the uncommitted changes in `../../../code_version/uncommitted.patch` (the code includes the post-evaluation fixes for F04, F11, F12 and F13).
