# Q34: report Unverified → retest Pass

**Prompt (Evaluation.pdf Appendix A):** There are two note proposals, one for ORD-001 and one for ORD-002. Confirm only ORD-001’s proposal.

**Report verdict:** Unverified (evidence M22)

**Report expected:** Confirm only the requested ID when both proposals really exist.

**Report observed:** Screenshot has no two pending notes. Source HTTP fixture exists; independent component test validates one selected ID and one untouched ID on same order.

**Retest verdict (main run):** Pass. Two pending notes; Confirm on ORD-001 only -> ORD-001 EXECUTED, ORD-002 still PROPOSED, one note.

**Files:** `main_run/` holds the full record (JSON: every request, answer, tool call with arguments and results, evidence rows, answer check, proposals, clicks and state reads) and a readable transcript (.md).

Model deepseek/deepseek-flash; prompt version f9348b4de425; code 290e5f7 plus the uncommitted changes in `../../../code_version/uncommitted.patch` (the code includes the post-evaluation fixes for F04, F11, F12 and F13).
