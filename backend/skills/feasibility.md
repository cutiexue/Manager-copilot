---
title: Feasibility and production scenarios
when: Can we take a new order or batch, by when, how cheaply, or how to allocate work between in-house production and workshops.
tools: estimate_in_house, estimate_production_plan, estimate_quickstitch, estimate_steadyhands, estimate_budgetworks, estimate_little_loom, estimate_giantweave, estimate_nimble_needle, estimate_oldmill, estimate_freshstart, optimize_fastest_plan, optimize_cheapest_plan, optimize_orders_cheapest, optimize_orders_outsourced, get_current_plan, revise_order_plan, query_orders
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
- Defaults: start on the reference date; include in-house production, zero in-house queue.
  Historical throughput and immediate availability are assumptions, not verified free capacity.
  In-house whole-batch stages are sequential; eligible producers may work in parallel.
- Never silently fill allocation gaps unless the user assigns the remainder in-house. Resolve
  ambiguous workshop names; A/B/C are not known IDs. W1 QuickStitch, W2 SteadyHands, W3 BudgetWorks,
  W4 Little Loom, W5 GiantWeave, W6 Nimble Needle, W7 OldMill, W8 FreshStart.
- Report estimated completion, allocation and external processing cost. In-house, transport and
  rework costs are excluded; currency is unspecified. Never call this total business cost.
  Report infeasible/search-limit results honestly; model-optimal does not mean guaranteed delivery.
