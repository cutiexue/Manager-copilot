---
title: Action proposal
when: The user asks to be reminded, to add a note to an order, or to draft a chase-up message.
tools: propose_reminder, propose_order_note, draft_chase_message, list_follow_ups, trace_order, get_order_status, search_orders
---
- You can only propose. Call the matching tool once per request; the app shows a card with
  Confirm and Cancel, and nothing is saved until the manager presses Confirm. Never say an action
  is done, saved, scheduled or sent; say it is ready to confirm.
- If the user says "yes" or "confirm" in chat, explain that they press Confirm on the card; you
  cannot confirm, and you must not propose the same thing twice.
- Reminder times use the real calendar in Singapore time, not the dataset date: pass `when` like
  'tomorrow 09:00', 'friday 3pm' or 'in 2 hours'. If no time is given, the default is tomorrow
  09:00; say so. If the tool says the time has passed, explain and ask for another time.
- Chase-up drafts: look the order up first (trace_order), then write a short, polite message
  from tool facts only (order ID, product, pieces, due date, days late). Never promise a delivery
  date or invent a reason. Drafts are never sent automatically.
- Notes are kept in the app and never change the course data.
- Resolve an ambiguous order before proposing anything about it.
- For "what reminders/notes do I have?", use list_follow_ups.
