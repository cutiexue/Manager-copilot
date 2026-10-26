---
title: One order's status
when: The user asks about one specific order: its stage, lateness, why it is at risk, or the evidence.
tools: get_order_status, trace_order, search_orders, get_customer_orders
---
- Use trace_order proactively for a specific order's computed overdue days and risk evidence.
  Order IDs work in any spelling (ORD-107, ord107, 107).
- For loose references ("the TrendCart hoodie order", "Maple's beanie"), call search_orders.
  Exactly one plausible match: answer about it and name it. Several: list them briefly with
  customer, product and due date, and ask which one. None: say so; do not pick a similar order.
- Unfinished orders normally have blank days_late/completed_date; blanks mean neither zero
  lateness nor an inability to compute it.
- If the user's premise contradicts the data (e.g. calls a late order on time, or asks why a
  finished order is stuck), correct it with the tool facts before answering.
