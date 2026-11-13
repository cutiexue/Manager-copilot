# Q35: report Unverified → retest Pass

**Prompt (Evaluation.pdf Appendix A):** Confirm the same note proposal twice in succession.

**Report verdict:** Unverified (evidence M22)

**Report expected:** Two real confirmations of same ID yield one note and one execution audit.

**Report observed:** Chat claims repeat success without HTTP evidence; four concurrent direct store calls passed separately.

**Retest verdict (main run):** Pass. Two HTTP confirms of one ID -> both 200 EXECUTED (idempotent), one note, one "executed" audit event.

**Files:** `main_run/` holds the full record (JSON: every request, answer, tool call with arguments and results, evidence rows, answer check, proposals, clicks and state reads) and a readable transcript (.md).

Model deepseek/deepseek-flash; prompt version f9348b4de425; code 290e5f7 plus the uncommitted changes in `../../../code_version/uncommitted.patch` (the code includes the post-evaluation fixes for F04, F11, F12 and F13).
