# Q43: report Fail → retest Pass

**Prompt (Evaluation.pdf Appendix A):** It is Monday, 30 March 2026. Show yesterday’s output, then show the previous working day’s output separately.

**Report verdict:** Fail (evidence M27)

**Report expected:** Use explicitly requested March 30 scenario: March 29 all zero; March 28 1,031/445/624/734.

**Report observed:** Used April 1 and returned March 31/March 30. Fails visible instruction; isolated clock/override configuration was not evidenced.

**Retest verdict (main run):** Pass. Uses the stated Monday 30 March: 29 March all zero (Sunday), 28 March 1,031/445/624/734 (fix for F12).

**Stability:** 3 runs → Pass, Pass, Pass. All 3 runs use 29 March (zero) and 28 March (1,031/445/624/734).

**Files:** `main_run/` holds the full record (JSON: every request, answer, tool call with arguments and results, evidence rows, answer check, proposals, clicks and state reads) and a readable transcript (.md); `rerun2/` and `rerun3/` hold the repeat runs.

Model deepseek/deepseek-flash; prompt version f9348b4de425; code 290e5f7 plus the uncommitted changes in `../../../code_version/uncommitted.patch` (the code includes the post-evaluation fixes for F04, F11, F12 and F13).
