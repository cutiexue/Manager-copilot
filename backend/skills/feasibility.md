---
title: Feasibility and production scenarios
when: Can we take a new order or batch, by when, how cheaply, how to allocate work between in-house production and workshops, or which workshops can make what.
tools: estimate_in_house, estimate_production_plan, estimate_quickstitch, estimate_steadyhands, estimate_budgetworks, estimate_little_loom, estimate_giantweave, estimate_nimble_needle, estimate_oldmill, estimate_freshstart, optimize_fastest_plan, optimize_cheapest_plan, optimize_orders_cheapest, optimize_orders_outsourced, get_current_plan, revise_order_plan, query_orders, list_workshops
---
- Use get_current_plan to inspect the last successful multi-order plan. For 'five more days'
  use revise_order_plan with extra_days=5: completion_date for explicitly later than completion,
  deadline_date for explicitly extending the requested deadline. If those dates differ and the
  user's meaning is unclear, ask which date. If no deadline exists, use completion_date and state
  that basis. Preserve the saved order scope and start date even if unrelated queries intervened.
  To keep only unfinished orders in that plan, use status=IN_PROGRESS; extra_days=0 retains
  the chosen date. Do not call a smaller scope's lower cost savings. Failed revisions leave the
  last successful plan current; do not describe that older plan as the failed requested revision.
  Cost reduction compares saved quotes; the fastest plan's cost was not minimized, so do not
  attribute all savings solely to waiting longer. These follow-ups support multi-order tools only.
- For minimum external processing charges for a group within a deadline, use
  optimize_orders_cheapest. Ask for a missing deadline; days include the start date.
  Distinguish the requested deadline from the plan's estimated completion date. For comparisons,
  keep order IDs, quantity basis and start date identical; do not invent a prior plan or savings.
  An infeasible result is not a complete delivery plan. Costs exclude transport and rework.
- For fastest all-outsourced production of a group of orders, use optimize_orders_outsourced.
  Before a NEW plan, re-query the scope named in the latest user exchange (e.g. overdue orders),
  not an earlier risk scope. Pass expected_order_count from that exchange to catch stale selection.
  Bare 'how soon can they finish' does not authorize assuming all-outsourced original-quantity
  reproduction. Ask once to confirm that scenario unless it was already explicitly accepted.
  This shares workshop capacity across categories. If the user explicitly asks to produce the
  original total quantities, compute directly and label the scenario. If they ask when existing
  work will finish, explain the missing remaining-work data and offer the original-quantity
  scenario with one short clarification. Never present it as a remaining-work forecast.
- Estimates and optimizers support new batches only. Existing-order remaining-stage scheduling
  is unsupported even with remaining quantities. Briefly explain this and confirm a clearly labeled
  new-batch reference scenario before changing scope; reuse known category and quantity.
- Use estimate_production_plan for a specified allocation, optimize_fastest_plan for earliest
  delivery, and optimize_cheapest_plan for minimum external charges within a requested deadline.
  Deadline days include the start date and are calendar days. Ask for a missing required deadline.
- Current load: by default in-house work queues behind the unfinished orders at each stage. That
  load counts every unfinished order in full from its current stage, so it is an upper bound on
  workload, not a guaranteed latest completion date; say so. Leave the queue parameters out unless the manager
  states a queue; never pass 0 to make the line look free.
- Say in-house is used only when uses_in_house is true (producers_used lists who makes it).
- Cheapest plans compare outside workshops only, because in-house cost is not in the data. Say
  that in-house was left out. Pass in_house_cost_per_piece only when the manager states one.
- Defaults: new plans start on the current data date (scenario_start_date), unless the user gives
  a different date. Report that start alongside data_as_of: capacity, queues and in-house reference
  load still use the 2026-04-01 data. Historical plans keep their saved start when revised.
  The fastest plan may use in-house production. Historical throughput is a scenario rate, not verified free capacity.
  In-house whole-batch stages are sequential; eligible producers may work in parallel.
- Which workshops can make something, or any other question about workshop profiles: call
  list_workshops and name every row it returns, marking suspended ones. Never build the list from
  plan or estimate results; they show only the workshops a plan used.
- Never silently fill allocation gaps unless the user assigns the remainder in-house. Resolve
  ambiguous workshop names; A/B/C are not known IDs. W1 QuickStitch, W2 SteadyHands, W3 BudgetWorks,
  W4 Little Loom, W5 GiantWeave, W6 Nimble Needle, W7 OldMill, W8 FreshStart.
- Report estimated completion, allocation and external processing cost. In-house, transport and
  rework costs are excluded; currency is unspecified. Never call this total business cost.
  Report infeasible/search-limit results honestly; model-optimal does not mean guaranteed delivery.
- Every outsourcing plan has `risk`. Start with risk.strategy_rating and risk.summary; for each
  workshop give its rework chance, dispatcher note and flags. A rework delays only that
  workshop's pieces. rework_scenario_arrival assumes one full redo at unchanged capacity, no new
  queue and fixed transport; it is not a latest-date guarantee. Actual delay is unknown.
- High-risk only: name risk_drivers and offer a safer option. Medium or low: just state it.
- Add one short line starting "Assumptions:" (e.g. start date, historical rates).
