# Sprint 3 changes

What changed after Sprint 2, why, and how it was checked. Tests: 260 passing (`cd backend && python -m pytest`).

## Data date

- "Today" is the date of the data the app is reading, not the real clock: 2026-04-01 for the course
  data, then 2 and 3 April for the scripted snapshots in `track1/scenarios/watch_snapshots.json`.
  Chat, briefing, watches and evidence all read the same date (`rules.today_iso()`).
- Loading the next snapshot on the Watches page moves the whole app to that day; simulated values
  are labelled in the evidence drawer.
- Tools that take a date default to the data date. Any other date needs `scenario=true`, so the model
  cannot ask about the real calendar by mistake.
- Reminders keep the real (Singapore) clock, and the interface shows both dates.

## Outsourcing risk

- Every outsourcing plan reports, per workshop: the chance a batch comes back defective
  (`defect_rate`, for the whole batch), the dispatcher note and flags from `workshops.csv`, and the
  latest arrival if the batch has to be redone.
- With a deadline it also reports the chance that a redo makes some pieces late. A redo delays only
  that workshop's pieces, not the whole plan.
- Plans are rated Low, Medium or High risk ("high-risk strategy" from a 20% chance of a redo).
  For High, the answer names what drives the risk and suggests a safer option.
- Code: `outsourcing_risk.py`, used by `production_estimates.py` and `production_optimizer.py`.

## Answer check

- After each answer, `answer_check.py` checks every order ID, date and figure in it against that
  turn's tool results, allowing for rounding, percentages and thousands separators.
- If figures appear with no tool call behind them, the model is asked once more. Anything still
  unmatched is listed under the answer.

## Fixes from the Evaluation Report V1

- Added period totals and week-on-week comparisons (`period_output.py`).
- Totals now come from tool fields such as `original_order_pieces` and `unfinished_order_pieces`, and
  the model is told never to add them up itself.
- Added top-N findings by type, the "due within N days" rule, and "those orders" across turns.
- Skills are shorter: lead with the answer, keep it short, state assumptions in one line, and end
  without offer questions.

## Evaluation (real DeepSeek model, 11 Nov 2026)

| Run | Held-out (30) | Development (17) |
|---|---|---|
| 1 | 26 | — |
| 2 | 26 | — |
| 3 | 29 | — |
| 4 | 29 | 15 |

- Run 4 scored 100% on answer correctness, numeric accuracy, evidence, multi-turn and action safety.
- Its remaining failures were wording, not data: an offer question at the end of one answer, a
  missing assumptions line, and 53 words where 50 were allowed. The Skills were adjusted for all
  three after run 4, and no run has been made since.
- Held-out case T1-EVAL-013 says "counting today", which conflicts with its expected answer. It
  needs a review by its owner and was not edited.
- Reports are in `evaluation/reports/<time>/`. Failures are in `evaluation/failure_ledger.jsonl`.
- Run everything with `run_evaluation.bat`.

## Interface

- Soft-UI look in the Neumorphism Light palette (#E0E5EC surface, #FFFFFF highlight, #A3B1C6
  shadow, #4D5B70 and #6D7C94 slate), with frosted panels and one dark slate card per page.
  Plus Jakarta Sans is bundled through npm, so the font works offline.
- Pages are reached through a floating dock at the bottom. Past conversations are listed beside the
  chat, and Ctrl+K searches pages, actions and conversations.
- Briefing: the summary sits on the dark card; each check is a module that opens in place.
- Orders page: every order can be filtered by due date, status, stage, customer or search. Totals
  and the stage chart come from the new `GET /orders` (`order_search.list_orders`), so the browser
  never adds anything up.
- Long tables in answers wrap their text and expand after 8 rows.
- The Actions and Watches pages reload every 30 seconds and when the window regains focus.
- Alerts are split into "Needs attention" and "System notices". Briefing rows show "Evidence",
  "Ask" and "Remind" next to their icons.
- Motion follows the pointer or answers a click, and turns off with the system's reduced-motion
  setting. Glass turns solid with reduced transparency.
- Windows: `start_app.bat` sets everything up on the first run and starts the app.
