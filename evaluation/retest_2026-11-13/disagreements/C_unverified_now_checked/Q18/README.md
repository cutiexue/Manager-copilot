# Q18: report Unverified → retest Pass

**Prompt (Evaluation.pdf Appendix A):** Turn 1: What is the current status of ORD-001? [Then update test data and ask again.] 9

**Report verdict:** Unverified (evidence M13)

**Report expected:** Change isolated fixture and query ORD-001 again; answer and source must change together.

**Report observed:** Only initial answer visible; no changed fixture or follow-up.

**Retest verdict (main run):** Pass. Adapted: the app updates data through scripted snapshots. Before: ASSEMBLY, 15 days overdue; after loading the 2 April snapshot: WASHING, 16 days overdue, stated as the 2026-04-02 snapshot.

**Files:** `main_run/` holds the full record (JSON: every request, answer, tool call with arguments and results, evidence rows, answer check, proposals, clicks and state reads) and a readable transcript (.md).

Model deepseek/deepseek-flash; prompt version f9348b4de425; code 290e5f7 plus the uncommitted changes in `../../../code_version/uncommitted.patch` (the code includes the post-evaluation fixes for F04, F11, F12 and F13).
