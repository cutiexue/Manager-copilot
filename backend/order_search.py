"""Free-text order search for the reminder dialog.

The browser never downloads the whole order book: matching runs here and the
result is capped, so the dialog stays fast however many orders exist. Matching
is case-insensitive over order ID, customer, product and stage, and every word
of the query must match. Risk reasons come from rules.py. Read-only.
"""

import re
from datetime import date

from data_loader import ORDERS_SOURCE, STAGES, load_orders, order_row_numbers, source_ref
from rules import risk_reasons, today_iso

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


def search_orders(query="", limit=8, as_of_date=None):
    """Find orders by ID, customer, product or stage; an empty query lists unfinished orders, at-risk first."""
    as_of_date = as_of_date or today_iso()
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
        "snapshot_date": today_iso(),
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
        "warnings": [] if as_of_date == today_iso() else [
            f"Uses order statuses from the {today_iso()} snapshot; other dates are scenarios, not historical or future facts."
        ],
    }


DUE_WINDOWS = {"all": None, "overdue": -1, "7d": 7, "30d": 30}
STATUS_FILTERS = ("all", "unfinished", "at_risk", "complete")


def list_orders(status="all", due="all", stage="", customer="", query="", as_of_date=None):
    """Every order for the Orders page, filtered, with the totals of what is shown.

    status: all, unfinished, at_risk or complete. due: all, overdue (unfinished and past due),
    7d or 30d (due from the data date to that many days later). stage and customer match exactly;
    query matches like search_orders. The totals are counted here, so the page never adds them up.
    """
    as_of_date = as_of_date or today_iso()
    if status not in STATUS_FILTERS:
        return {"status": "error", "message": f"status must be one of {STATUS_FILTERS}."}
    if due not in DUE_WINDOWS:
        return {"status": "error", "message": f"due must be one of {tuple(DUE_WINDOWS)}."}
    if not isinstance(query, str) or len(query) > MAX_QUERY_LENGTH:
        return {"status": "error", "message": f"Query must be text of at most {MAX_QUERY_LENGTH} characters."}
    ref = date.fromisoformat(as_of_date)
    rows = order_row_numbers()
    words = query.split()
    shown = []
    customers, stages = set(), set()
    for order in load_orders():
        customers.add(order["customer"])
        stages.add(order["current_stage"])
        reasons = risk_reasons(order, ref)
        unfinished = order["status"] == "IN_PROGRESS"
        if status == "unfinished" and not unfinished:
            continue
        if status == "complete" and unfinished:
            continue
        if status == "at_risk" and not reasons:
            continue
        due_in = (date.fromisoformat(order["due_date"]) - ref).days
        window = DUE_WINDOWS[due]
        if window == -1 and not (unfinished and due_in < 0):
            continue
        if window not in (None, -1) and not 0 <= due_in <= window:
            continue
        if stage and order["current_stage"] != stage:
            continue
        if customer and order["customer"] != customer:
            continue
        if words and None in [_word_rank(order, word) for word in words]:
            continue
        shown.append((order, reasons))
    shown.sort(key=lambda item: (item[0]["status"] != "IN_PROGRESS", not item[1], item[0]["due_date"], item[0]["order_id"]))

    by_stage = {name: 0 for name in STAGES + ("COMPLETE",)}
    for order, _ in shown:
        by_stage[order["current_stage"]] += 1
    return {
        "status": "ok",
        "as_of_date": ref.isoformat(),
        "filters": {"status": status, "due": due, "stage": stage, "customer": customer, "query": query},
        "summary": {
            "orders": len(shown),
            "unfinished": sum(o["status"] == "IN_PROGRESS" for o, _ in shown),
            "at_risk": sum(bool(r) for _, r in shown),
            "pieces": sum(int(o["pieces"]) for o, _ in shown),
            "by_stage": [{"stage": name, "orders": count} for name, count in by_stage.items()],
        },
        "customers": sorted(customers),
        "stages": [name for name in STAGES + ("COMPLETE",) if name in stages],
        "orders": [
            {
                "order_id": o["order_id"], "customer": o["customer"], "product": o["product"],
                "category": o["category"], "pieces": int(o["pieces"]), "due_date": o["due_date"],
                "status": o["status"], "current_stage": o["current_stage"],
                "last_activity_date": o["last_activity_date"], "risk_reasons": r,
                "source_row": rows[o["order_id"]],
            }
            for o, r in shown
        ],
        "source": ORDERS_SOURCE,
    }
