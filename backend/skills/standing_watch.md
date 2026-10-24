---
title: Standing watch
when: The user wants to be told if or when something happens to an order ("tell me if ORD-062 hasn't moved by Thursday", "let me know when ORD-107 ships").
tools: propose_watch, get_order_status, search_orders, list_follow_ups
---
- Map the request to one condition: not_moved_by (needs a deadline), becomes_overdue, completed,
  or reaches_stage (needs a stage). Resolve the order first if it is ambiguous.
- Watch deadlines use the dataset calendar, where today is Wednesday 2026-04-01: "by Thursday" is
  2026-04-02, "by Friday" 2026-04-03, "next Monday" 2026-04-06. State the date you used.
- Call propose_watch once. Then say the watch appears as a card and starts only when the manager
  presses Confirm. Never say it is active, set or saved before that.
- Watches are checked against scripted data snapshots (the course data never changes), so say
  alerts demonstrate the mechanism rather than live factory events when that matters.
- If propose_watch refuses (the order is already complete, already overdue or already past that
  stage), explain why and offer a condition that can still happen.
- Conditions on output levels, customers or anything other than one order are not supported as
  watches; say so and offer an order watch or a reminder instead.
- For "what am I watching?", use list_follow_ups with kind="watches".
