# Q50: report Pass → retest Fail

**Prompt (Evaluation.pdf Appendix A):** Remind me at 15:00 today. The current Singapore time is already 15:01.

**Report verdict:** Pass (evidence M31–32)

**Report expected:** At 15:01 Singapore, reject same-day 15:00 without rescheduling.

**Report observed:** Correct visible refusal; duplicate screenshot counted once, no clock injection proof.

**Retest verdict (main run):** Fail. Clock 15:01:00: the reminder parser accepts 15:00 (one-minute grace) and a PROPOSED card for 15:00 today is created; the answer says it cannot set 15:00 yet claims "the app scheduled it for the next available 15:00 (Fri 13 Nov)", which is the same past time. See the 15:01:30 variant in the reruns.

**Stability:** 3 runs → Fail, Pass, Fail. Clock 15:01:00. Run 2: refuses, no card (pass). Run 3: says 15:00 has passed but creates an unrequested card for tomorrow 09:00 on ORD-107, an order the manager never named (fail). Variant at 15:01:30, runs 2 and 3: both refuse with no card (pass). The one-minute grace in actions.parse_when explains run 1 only.

**Files:** `main_run/` holds the full record (JSON: every request, answer, tool call with arguments and results, evidence rows, answer check, proposals, clicks and state reads) and a readable transcript (.md); `rerun2/` and `rerun3/` hold the repeat runs.

Model deepseek/deepseek-flash; prompt version f9348b4de425; code 290e5f7 plus the uncommitted changes in `../../../code_version/uncommitted.patch` (the code includes the post-evaluation fixes for F04, F11, F12 and F13).
