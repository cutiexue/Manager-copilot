# Real-model retest, 13 November 2026

An independent real-model rerun of the whole evaluation after the fixes for the failures reported in
[Evaluation.pdf](../report/Evaluation.pdf). It runs the automated sets in this repository and every
Evaluation.pdf question (Q01–Q70). Each verdict that differs from the report is kept with its full evidence.
A Chinese version of this summary is in [RETEST_SUMMARY_zh.md](./RETEST_SUMMARY_zh.md).

## What was run

| Item | Value |
|---|---|
| Time | 13 Nov 2026, 11:50–12:04 Singapore time |
| Model | DeepSeek `deepseek-flash`, the same model as the archived runs in `evaluation/reports/` |
| Code | `290e5f7` plus the changes in [code_version/uncommitted.patch](./code_version/uncommitted.patch), which include the fixes for F04, F11, F12 and F13. Those changes are committed together with this folder. |
| Prompt version | `f9348b4de425` |
| Data | The course CSVs, with the same SHA-256 as the report: orders `0880af9742fe`, production_log `f67e505bd460`, workshops `d7e1c97d3d33` |
| Isolation | A fresh temporary SQLite database per scenario; no app instance, user database or repository ledger was touched |

The retest has three parts:

1. **Automated sets** (`automated/`): the 30-case evaluation set and the 17-case development set, scored by
   `evaluation/run_evaluation.py`.
2. **Every Evaluation.pdf question** (`report_questions/`): Q01–Q70, using the prompts in Appendix A
   verbatim. Manager clicks (Confirm, Cancel, two tabs confirming at once), proposal expiry, reminder firing,
   data-snapshot changes and clock settings go through the same HTTP routes or store methods the app uses.
   The application state is read before and after each of these steps.
3. **Repeat runs** (`reruns/run2`, `reruns/run3`): two more runs of every question whose verdict differs from
   the report, to see whether the difference is stable.

## Results

### Automated sets

| Set | Result | Notes |
|---|---|---|
| Evaluation set, 30 cases | 30/30; behaviour 40/40 turns, numeric facts 74/74, tool selection 30/30 | The archived run scored 29/30 |
| Development set, 17 cases | 15/17 | Both failures are scorer artefacts on review, and both answers are correct. DEV-001 ends with an offer ("Want a chase-up draft?") that the scorer read as a clarifying question. DEV-014 correctly says ORD-150 does not exist, but its date was counted as numbers without source rows. |

### Evaluation.pdf questions (main run)

| Set | Evaluation.pdf | Retest |
|---|---|---|
| Q01–Q40 development regression | 31 pass, 1 partial, 1 fail, 7 unverified | 38 pass, 2 partial |
| Q41–Q56 exposed validation | 6 pass, 1 partial, 1 fail, 8 unverified | 14 pass, 1 partial, 1 fail |
| Q57–Q70 independent test | 8 pass, 2 partial, 4 unverified | 13 pass, 1 partial |

The fixes were made in response to Q08, Q42, Q43 and Q60, and Q60 belongs to the independent test set. For the
fixed code, Q57–Q70 is therefore no longer fully held out; without Q60 the independent set scores 12 of 13.
One reviewer graded every answer; there was no second reviewer. Each verdict and its reason is in
[grading_main_run.json](./grading_main_run.json).

## Verdicts that differ from Evaluation.pdf

Each question has its own folder under [disagreements/](./disagreements/). It holds a README with the report's
prompt, expected answer, observation and verdict, our verdict and stability, plus the full record and a readable
transcript of every run.

### A. Worse than the report

| Q | Report | Retest | 3 runs | Finding |
|---|---|---|---|---|
| Q36 | Pass | Partial | Partial ×3 | Clarifies "O1", but never says that 2 April 2026 15:00 has already passed, and promises to set the reminder for that time once the order is known. `propose_reminder` rejects the unknown order before it checks the time. |
| Q50 | Pass | Fail | Fail, Pass, Fail | Clock at 15:01:00. Run 1: a card for 15:00 today is created (the time parser allows one minute of grace), and the answer claims it was rescheduled. Run 3: the model picks ORD-107, which the manager never named, and creates a card for tomorrow 09:00. At 15:01:30 both variant runs refuse correctly. |
| Q14 | Pass | Partial | Partial, Pass, Pass | Run 1 gives Knitting's 7-day baseline (939) as Assembly's (515.7). Runs 2 and 3 are correct. Intermittent. |

### B. Better than the report

| Q | Report | Retest | 3 runs | Reason |
|---|---|---|---|---|
| Q08 | Fail | Pass | Pass ×3 | New `list_workshops` tool lists all seven TOPS workshops and marks W7 suspended |
| Q43 | Fail | Pass | Pass ×3 | Rule for a stated "today" |
| Q42 | Partial | Pass | Pass ×3 | `get_overdue_orders` returns the customer grouping and count |
| Q60 | Partial | Pass | Pass ×3 | Each order carries its own overdue days; the answer check catches misattribution |
| Q20 | Partial | Pass | Pass ×3 | Asks which order is meant |
| Q66 | Partial | Pass | – | Independently verified as the minimum external charge under the system's timing model ([q66_optimality_check.txt](./q66_optimality_check.txt)) |

Group B reflects code changed after the evaluation. It does not show that the report graded the earlier code
wrongly.

### C. Unverified in the report, now checked (19 questions)

- **Pass (17):** Q18, Q33, Q34, Q35, Q37, Q38, Q39, Q46, Q47, Q48, Q51, Q52, Q53, Q54, Q67, Q68, Q70.
  - Nothing is written before Confirm, and nothing is saved after Cancel.
  - With two proposals, only the confirmed one executes. Confirming one proposal twice, or from two tabs at
    once, executes it once.
  - An expired proposal returns 409.
  - A reminder fires once, in its minute.
  - Watches trigger or resolve on the scripted snapshots, and cancelling one leaves the other active.
  - Drafts are saved, never sent.
- **Partial (2):**
  - Q49: the system saved one note in all three runs, but no answer said so, and run 1 suggested there could
    be two.
  - Q69: the reminder fired at 09:00 in all three runs, but run 1 called Saturday 14 November "Thursday"
    (intermittent).

## Issues found by the retest (not in Evaluation.pdf)

1. **Reminder validation order (Q36):** an unknown order is reported without checking the time, so the model
   cannot tell that the time has passed.
2. **Past-time grace (Q50):** at 15:01:00 a 15:00 reminder is still accepted. The model may also attach a
   reminder to an order the manager did not name.
3. **Undocumented guarantee (Q49):** a confirmed proposal executes once, but the Skills do not say so, so the
   model will not promise it.
4. **Stage figures attached to the wrong stage (Q14, intermittent):** the attribution check covers order overdue
   days only.
5. **Answer-check false positives:** in a cited row range or list ("rows 239–359", "rows 81, 85, 86") every row
   after the first is flagged as unverified. Evaluation.pdf noted the same for Q57 and Q58.

## Limits

- One model (`deepseek-flash`). One main run per question, and two repeat runs only for the questions whose
  verdict changed.
- A few questions need a step the report did not spell out; each scenario record states its adaptation:
  - Q17 and Q56 add a setup turn.
  - Q18 changes data through the scripted snapshot (ORD-120) instead of editing ORD-001.
  - Q37 and Q38 add a reply naming the order behind "O1".
  - Q50 and Q51 set the clock.
- Clock settings replace the app's Singapore clock inside the test process; no real waiting.
- The code includes the post-evaluation fixes; Evaluation.pdf assessed an earlier build.

## Files

| Path | Contents |
|---|---|
| `code_version/` | HEAD, the uncommitted patch that was tested, new files and SHA-256 of every file |
| `automated/` | Full results of both automated sets (`results.jsonl`, `run.json`, `summary.md`, logs) |
| `report_questions/scenarios/` | Full record of every Q01–Q70 scenario (JSON): requests, answers, tool calls with arguments and results, evidence rows, answer check, proposals, clicks and state reads |
| `report_questions/transcripts/` | The same records as readable transcripts |
| `report_questions/run_full.json` | Version record of the main run. A later Q67-only rerun overwrote the original file; it was rebuilt from the scenario records, as its `note` field explains |
| `report_questions/superseded/` | The first Q67 record. The harness looked for a proposal of kind `draft` instead of `chase_message`; it was fixed and Q67 rerun |
| `reruns/run2`, `reruns/run3` | The two repeat runs |
| `disagreements/` | The 28 questions whose verdict differs from Evaluation.pdf, one folder each |
| `grading_main_run.json` | Verdict and reason for all 70 questions |
| `report_expectations.json` | Prompt, expected answer and verdict of each question, taken from Evaluation.pdf Appendix A |
| `q66_optimality_check.txt` | Independent check of the Q66 minimum charge |
| `harness/` | The scripts that ran and rendered the retest |

Changes made when this folder was copied into the repository:

- The local project path in the three run logs is replaced with `<local project folder>`.
- The two shell scripts now find the repository root relative to this folder.

The Python harness is unchanged; its SHA-256 is recorded in the run files.

## Reproducing

With a key in `backend/.env` (see `backend/.env.example`), from the repository root:

```bash
bash evaluation/retest_2026-11-13/harness/run_all.sh
```

To check the harness without a key, from `backend/`:

```bash
.venv/bin/python ../evaluation/retest_2026-11-13/harness/retest_report_questions.py --fake --out /tmp/retest
```

Write new runs to a new folder. `run_all.sh` writes into this folder and replaces what is here.
