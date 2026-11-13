# Q70: report Unverified → retest Pass

**Prompt (Evaluation.pdf Appendix A):** Watch ORD-114 until the agreed cutoff and alert me only if it hasn’t moved.

**Report verdict:** Unverified (evidence H14)

**Report expected:** (see report text)

**Report observed:** Correctly asks for the missing cutoff and does not invent an agreed date. The example April 3 is explicitly illustrative. Clarification behavior passes, but no configured watch, unchanged/updated fixture or resulting alert is shown; the full watch-trigger scenario remains unverified.

**Retest verdict (main run):** Pass. Asks for the cutoff and invents none. No watch exists to trigger, by design of the prompt; triggering is covered by Q52/Q53.

**Files:** `main_run/` holds the full record (JSON: every request, answer, tool call with arguments and results, evidence rows, answer check, proposals, clicks and state reads) and a readable transcript (.md).

Model deepseek/deepseek-flash; prompt version f9348b4de425; code 290e5f7 plus the uncommitted changes in `../../../code_version/uncommitted.patch` (the code includes the post-evaluation fixes for F04, F11, F12 and F13).
