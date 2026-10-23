"""Free-text order search for the reminder dialog.

The browser never downloads the whole order book: matching runs here and the
result is capped, so the dialog stays fast however many orders exist. Matching
is case-insensitive over order ID, customer, product and stage, and every word
of the query must match. Risk reasons come from rules.py. Read-only.
"""

import re
from datetime import date

from data_loader import ORDERS_SOURCE, load_orders, order_row_numbers, source_ref
from rules import SNAPSHOT, risk_reasons

MAX_LIMIT = 50
MAX_QUERY_LENGTH = 200


def _word_rank(order, word):
    """0 exact order ID, 1 partial ID, 2 customer, 3 product or stage; None when the word does not match."""
    order_id = order["order_id"].casefold()
    compact_id = order_id.replace("-", "")
    digits = re.sub(r"\D", "", order_id)
    word = word.casefold()
    # "ORD-002"、"ord002"、"2" 都指同一个订单。
    if word in (order_id, compact_id) or (word.isdigit() and digits and int(word) == int(digits)):
        return 0
    if word in order_id or word in compact_id:
        return 1
    if word in order["customer"].casefold():
        return 2
    if word in order["product"].casefold() or word == order["current_stage"].casefold():
        return 3
    return None


def search_orders(query="", limit=8, as_of_date=SNAPSHOT):
    """Find orders by ID, customer, product or stage; an empty query lists unfinished orders, at-risk first."""
    if not isinstance(query, str) or len(query) > MAX_QUERY_LENGTH:
        return {"status": "error", "message": f"Query must be text of at most {MAX_QUERY_LENGTH} characters."}
    if type(limit) is not int or not 1 <= limit <= MAX_LIMIT:
        return {"status": "error", "message": f"limit must be an integer from 1 to {MAX_LIMIT}."}
    try:
        ref = date.fromisoformat(as_of_date)
    except (TypeError, ValueError):
        return {"status": "error", "message": "Use a valid date in YYYY-MM-DD format."}

    words = query.split()
    rows = order_row_numbers()
    matches = []
    for order in load_orders():
        reasons = risk_reasons(order, ref)
        if words:
            ranks = [_word_rank(order, word) for word in words]
            if None in ranks:
                continue
            rank = max(ranks)
        elif order["status"] == "IN_PROGRESS":
            rank = 0
        else:
            continue
        # 匹配程度相同时：未完成在前，有风险的在前，到期早的在前。
        key = (rank, order["status"] != "IN_PROGRESS", not reasons, order["due_date"], order["order_id"])
        matches.append((key, order, reasons))
    matches.sort(key=lambda match: match[0])
    selected = matches[:limit]

    return {
        "status": "ok",
        "query": query,
        "as_of_date": ref.isoformat(),
        "snapshot_date": SNAPSHOT,
        "total": len(matches),
        "count": len(selected),
        "orders": [
            {
                "order_id": order["order_id"], "customer": order["customer"], "product": order["product"],
                "category": order["category"], "pieces": int(order["pieces"]), "due_date": order["due_date"],
                "status": order["status"], "current_stage": order["current_stage"],
                "last_activity_date": order["last_activity_date"], "risk_reasons": reasons,
                "source_row": rows[order["order_id"]],
            }
            for _, order, reasons in selected
        ],
        "source": ORDERS_SOURCE,
        "source_rows": [source_ref(ORDERS_SOURCE, rows[order["order_id"]], order["order_id"])
                        for _, order, _ in selected],
        "warnings": [] if as_of_date == SNAPSHOT else [
            f"Uses order statuses from the {SNAPSHOT} snapshot; other dates are scenarios, not historical or future facts."
        ],
    }
