---
title: Morning briefing
when: The user asks for the morning briefing, what needs attention today, or a scan for issues.
tools: get_morning_briefing, discover_issues, get_orders_at_risk, compare_stage_output, get_stage_output, list_follow_ups
---
- Use get_morning_briefing for briefings and discover_issues for issue scans.
- Label yesterday's comparison separately from recent-period comparisons: the last workday is
  compared with the previous 7 workdays; discovery compares the last 3 workdays with the 7 before.
  On a Monday the briefing reports Saturday; call it the last workday, not yesterday.
- Findings are grouped by type, not on a universal severity scale. Each check marks items as
  act now or watch by its own stated rule; report that rule rather than ranking across types.
- Suggestions are follow-up checks, not decisions to change delivery promises.
- A decrease alone is not a diagnosis or forecast. Risk thresholds are provisional rules; report
  identified reasons without implying all possible risks have been ruled out.
- For "what needs my attention today", also check list_follow_ups for unread alerts and due
  reminders, and mention them after the briefing's findings.
