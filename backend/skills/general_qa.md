---
title: General questions about orders and output
when: Counts, lists, filters, totals, customers, overdue or at-risk orders, and stage output or comparisons.
tools: query_orders, get_overdue_orders, get_orders_at_risk, get_customer_orders, search_orders, get_stage_output, compare_stage_output
---
- Every order count/list follow-up needs a fresh matching query, even if history contains the
  answer. In particular risk list -> overdue count MUST call get_overdue_orders again, so the
  selected scope becomes the overdue orders, not the earlier broader risk list.
  If describing only a subset of a tool result (e.g. due-soon orders), call query_orders with
  scope='all' and those exact order_ids before answering, to select the subset actually discussed.
- For category lists use query_orders.by_category.order_ids and orders, never infer category
  from product names or divide a flat list yourself. One order per table row. For simple counts,
  give one concise sentence; omit repeated caveats and unsolicited offers to investigate further.
- Use query_orders for counts, filters and quantity totals. For an unqualified order count,
  report all orders and the status breakdown. Quantities are original pieces, not remaining work.
- For 'these orders' use scope='selected'; it restores the last explicit order query in this
  conversation, including an empty set. Use scope='all' for an explicit fresh/all-order query.
  Apply further filters within the selected set. If the reference is ambiguous, ask one short
  question. Never silently replace an empty or missing selection with all orders.
- Query the selected set before answering its totals. Mixed categories are reported separately;
  independent batch estimates cannot establish a shared-capacity multi-order completion time.
- Customer names may be partial ('maple' is Maple & Co). If a tool says it read a partial name as
  one customer, say which; if it returns several candidates, ask which customer is meant.
- Select tools by their descriptions. Pass the requested baseline_days and due_within_days.
