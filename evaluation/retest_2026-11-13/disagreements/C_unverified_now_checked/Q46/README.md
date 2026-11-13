# Q46: report Unverified → retest Pass

**Prompt (Evaluation.pdf Appendix A):** Turn 1: What is the due date of ORD-002? Turn 2 after an isolated CSV update: What is its due date now?

**Report verdict:** Unverified (evidence None)

**Report expected:** Change ORD-002 due date from March 29 to April 6 in isolated fixture and re-query.

**Report observed:** No paired data-edit run supplied.

**Retest verdict (main run):** Pass. After the isolated CSV edit the answer changes to 2026-04-06 and no longer overdue.

**Files:** `main_run/` holds the full record (JSON: every request, answer, tool call with arguments and results, evidence rows, answer check, proposals, clicks and state reads) and a readable transcript (.md).

Model deepseek/deepseek-flash; prompt version f9348b4de425; code 290e5f7 plus the uncommitted changes in `../../../code_version/uncommitted.patch` (the code includes the post-evaluation fixes for F04, F11, F12 and F13).
