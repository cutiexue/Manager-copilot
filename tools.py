"""Provide tools for querying factory data."""

from datetime import date, timedelta

from data_loader import (ORDERS_SOURCE, PRODUCTION_SOURCE, load_orders,
                         load_production, order_row_numbers,
                         production_row_numbers, source_ref)
from rules import (DUE_SOON_DAYS, RECENT_WORKDAYS, SNAPSHOT, is_overdue,
                   previous_workdays, risk_reasons)
from order_selection import current_selection


def query_orders(scope='all', status=None, customer=None, category=None,
                 due_from=None, due_to=None, order_ids=None):
    """Filter orders and compute exact counts and original quantities."""
    if scope not in ('all', 'selected'):
        return {'status': 'error', 'message': 'scope must be all or selected.'}
    if status not in (None, 'IN_PROGRESS', 'COMPLETE') or category not in (None, 'TOPS', 'ACCESSORIES'):
        return {'status': 'error', 'message': 'Invalid status or category.'}
    if customer is not None and (not isinstance(customer, str) or not customer.strip()):
        return {'status': 'error', 'message': 'customer must be a non-empty string.'}
    if order_ids is not None and (not isinstance(order_ids, list) or any(
            not isinstance(value, str) or not value.strip() for value in order_ids)):
        return {'status': 'error', 'message': 'order_ids must be a list of non-empty strings.'}
    try:
        lower = date.fromisoformat(due_from) if due_from is not None else None
        upper = date.fromisoformat(due_to) if due_to is not None else None
    except (ValueError, TypeError):
        return {'status': 'error', 'message': 'Use valid YYYY-MM-DD due dates.'}
    if lower and upper and lower > upper:
        return {'status': 'error', 'message': 'due_from must not be after due_to.'}
    rows = load_orders()
    source_rows = {row['order_id']: index + 2 for index, row in enumerate(rows)}
    selected = current_selection() if scope == 'selected' else None
    if scope == 'selected' and selected is None:
        return {'status': 'needs_clarification', 'message': 'No order selection exists in this conversation. Ask which orders are meant.'}
    base_ids = set(selected['order_ids']) if selected is not None else set(source_rows)
    missing = base_ids - set(source_rows)
    if missing:
        return {'status': 'insufficient_data', 'message': 'Previously selected orders are absent from the source.',
                'missing_order_ids': sorted(missing)}
    if order_ids is not None:
        requested = {value.strip() for value in order_ids}
        missing = requested - set(source_rows)
        if missing:
            return {'status': 'not_found_ids', 'message': 'Some requested orders do not exist; no partial total was calculated.',
                    'missing_order_ids': sorted(missing)}
        base_ids &= requested
    matches = []
    for row in rows:
        if row['order_id'] not in base_ids:
            continue
        if status and row['status'] != status:
            continue
        if category and row['category'] != category:
            continue
        if customer and row['customer'].strip().casefold() != customer.strip().casefold():
            continue
        due = date.fromisoformat(row['due_date'])
        if (lower and due < lower) or (upper and due > upper):
            continue
        matches.append(row)

    def grouped(field):
        groups = {}
        for row in matches:
            bucket = groups.setdefault(row[field], {'order_count': 0, 'original_order_pieces': 0,
                                                    'order_ids': []})
            bucket['order_count'] += 1
            bucket['original_order_pieces'] += int(row['pieces'])
            bucket['order_ids'].append(row['order_id'])
        return groups

    filters = {key: value for key, value in dict(status=status, customer=customer,
               category=category, due_from=due_from, due_to=due_to, order_ids=order_ids).items() if value is not None}
    ids = [row['order_id'] for row in matches]
    return {
        'status': 'ok', 'snapshot_date': SNAPSHOT, 'count': len(matches),
        'original_order_pieces': sum(int(row['pieces']) for row in matches),
        'by_status': grouped('status'), 'by_category': grouped('category'),
        'order_ids': ids, 'filters': filters, 'scope': scope,
        'orders': [{key: row[key] for key in ('order_id', 'category', 'customer', 'pieces', 'due_date', 'status')}
                   for row in matches],
        'selection': {'order_ids': ids, 'filters': filters,
                      'source_tool': 'query_orders'},
        'source': ORDERS_SOURCE,
        'source_rows': [source_ref(ORDERS_SOURCE, source_rows[value], value) for value in ids],
        'warnings': ['Quantities are original ordered pieces, not remaining work. No remaining quantity is supplied.'],
    }


def _order_refs(selected):
    """Build source-row citations for the given orders."""
    rows = order_row_numbers()
    return [source_ref(ORDERS_SOURCE, rows[order["order_id"]], order["order_id"])
            for order in selected]


def get_order_status(order_id):
    """Return the matching order or a not_found result."""
    # 读取全部订单。
    orders = load_orders()

    # 按订单编号精确匹配。
    for order in orders:
        if order["order_id"] == order_id:
            return {"status": "ok", "data": order,
                    "source": ORDERS_SOURCE,
                    "source_rows": _order_refs([order])}

    return {"status": "not_found", "data": None}


def get_customer_orders(customer):
    """Return all orders matching a customer name, ignoring case and outer spaces."""
    orders = load_orders()
    matched_orders = []

    # 只处理内存里的查询文本，不修改 CSV。
    customer_name = customer.strip().casefold()
    for order in orders:
        if order["customer"].strip().casefold() == customer_name:
            matched_orders.append(order)

    # 查完所有订单后再返回，避免只返回第一条。
    if matched_orders:
        return {"status": "ok", "count": len(matched_orders), "data": matched_orders,
                "source": ORDERS_SOURCE,
                "source_rows": _order_refs(matched_orders)}

    return {"status": "not_found", "count": 0, "data": []}


def get_stage_output(stage, production_date):
    """Return recorded factory-wide output for one stage on one day."""
    # 先检查工序和日期，再读取数据。
    if not isinstance(stage, str):
        return {"status": "error", "message": "Stage must be a string."}
    stage = stage.strip().upper()
    if stage not in {"KNITTING", "ASSEMBLY", "WASHING", "PACKING"}:
        return {"status": "error", "message": "Use KNITTING, ASSEMBLY, WASHING, or PACKING."}
    try:
        query_date = date.fromisoformat(production_date).isoformat()
    except (TypeError, ValueError):
        return {"status": "error", "message": "Use a valid date in YYYY-MM-DD format."}

    for record in load_production():
        if record["stage"] == stage and record["date"] == query_date:
            # 只在内存副本中把数量转换成整数。
            result = record.copy()
            result["pieces_completed"] = int(record["pieces_completed"])
            row_number = production_row_numbers()[(query_date, stage)]
            return {
                "status": "ok",
                "data": result,
                "source": PRODUCTION_SOURCE,
                "source_rows": [source_ref(PRODUCTION_SOURCE, row_number,
                                           f"{query_date} {stage}")],
            }

    # 没有记录不代表产量为零。
    return {
        "status": "not_found",
        "data": None,
        "message": "No production record for this stage and date. Missing data is not zero output.",
    }


def compare_stage_output(stage, production_date, baseline_days=7):
    """Compare actual output with a configurable number of previous workdays."""
    # bool 在 Python 中也属于整数，因此这里使用 type 严格检查。
    if type(baseline_days) is not int or baseline_days <= 0:
        return {"status": "error", "message": "baseline_days must be a positive integer."}
    current = get_stage_output(stage, production_date)
    if current["status"] != "ok":
        return current

    target = current["data"]
    target_date = date.fromisoformat(target["date"])
    if target_date.weekday() == 6:
        return {
            "status": "not_applicable",
            "data": target,
            "source": current["source"],
            "message": "Sunday is a scheduled rest day; no workday comparison is made.",
        }

    records = load_production()
    available_days = {
        r["date"] for r in records
        if r["stage"] == target["stage"]
        and date.fromisoformat(r["date"]) < target_date
        and date.fromisoformat(r["date"]).weekday() != 6
    }
    if len(available_days) < baseline_days:
        return {
            "status": "insufficient_data",
            "data": target,
            "source": current["source"],
            "message": f"Need {baseline_days} previous workdays; only {len(available_days)} are available.",
        }

    # 向前寻找指定数量的工作日，不含目标当天，也不跳过缺失的工作日。
    baseline_dates = [day.isoformat() for day in previous_workdays(target_date, baseline_days)]

    baseline_records = []
    for record in records:
        if record["stage"] == target["stage"] and record["date"] in baseline_dates:
            baseline_records.append({
                "date": record["date"],
                "stage": record["stage"],
                "pieces_completed": int(record["pieces_completed"]),
            })

    # 每个基准日期必须恰好有一条记录，缺失或重复都不继续计算。
    for baseline_date in baseline_dates:
        matches = [r for r in baseline_records if r["date"] == baseline_date]
        if len(matches) != 1:
            return {
                "status": "insufficient_data",
                "data": target,
                "source": current["source"],
                "message": f"Need exactly one record for each of the previous {baseline_days} workdays.",
                "problem_date": baseline_date,
            }

    # 给每条基准记录补上它在 CSV 里的行号，方便从数字回溯到原始行。
    row_numbers = production_row_numbers()
    for record in baseline_records:
        record["source_row"] = row_numbers[(record["date"], record["stage"])]

    average = sum(r["pieces_completed"] for r in baseline_records) / baseline_days
    difference = target["pieces_completed"] - average
    # 基准为零时不能做除法；保留数量差值，百分比返回空值。
    change_percent = difference / average * 100 if average != 0 else None
    return {
        "status": "ok",
        "data": {
            **target,
            "baseline_workdays": baseline_days,
            "baseline_average": round(average, 2),
            "difference_pieces": round(difference, 2),
            "change_percent": round(change_percent, 2) if change_percent is not None else None,
        },
        "baseline_records": sorted(baseline_records, key=lambda r: r["date"]),
        "source": current["source"],
        "source_rows": current["source_rows"],
        "warnings": ["A historical comparison is not an anomaly diagnosis or a forecast."],
    }


def get_overdue_orders(as_of_date=SNAPSHOT):
    """Find unfinished orders past their due date using the stored snapshot."""
    # 把日期文本转换成日期对象，才能比较日期和计算天数。
    try:
        reference_date = date.fromisoformat(as_of_date)
    except (TypeError, ValueError):
        return {"status": "error", "message": "Use a valid date in YYYY-MM-DD format."}

    orders = load_orders()
    overdue_orders = []
    for order in orders:
        if is_overdue(order, reference_date):
            # 复制到内存里的新字典，再添加计算结果；不改原始记录或文件。
            result = order.copy()
            result["overdue_calendar_days"] = (reference_date - date.fromisoformat(order["due_date"])).days
            overdue_orders.append(result)

    return {
        "status": "ok",
        "as_of_date": reference_date.isoformat(),
        "snapshot_date": SNAPSHOT,
        "count": len(overdue_orders),
        "original_order_pieces": sum(int(order['pieces']) for order in overdue_orders),
        "data": overdue_orders,
        "source": ORDERS_SOURCE,
        "source_rows": _order_refs(overdue_orders),
        "warnings": [] if as_of_date == SNAPSHOT else [
            f"Uses order statuses from the {SNAPSHOT} snapshot; other dates are scenarios, not historical or future facts."
        ],
    }


def get_orders_at_risk(as_of_date=SNAPSHOT, due_within_days=DUE_SOON_DAYS):
    """List unfinished orders that are overdue, due soon, or have gone quiet."""
    try:
        reference_date = date.fromisoformat(as_of_date)
    except (TypeError, ValueError):
        return {"status": "error", "message": "Use a valid date in YYYY-MM-DD format."}
    if type(due_within_days) is not int or due_within_days <= 0:
        return {"status": "error", "message": "due_within_days must be a positive integer."}

    orders = load_orders()
    at_risk = []
    for order in orders:
        reasons = risk_reasons(order, reference_date, due_within_days)
        if reasons:
            result = order.copy()
            result["risk_reasons"] = reasons
            at_risk.append(result)

    return {
        "status": "ok",
        "as_of_date": reference_date.isoformat(),
        "snapshot_date": SNAPSHOT,
        "count": len(at_risk),
        "data": at_risk,
        "source": ORDERS_SOURCE,
        "source_rows": _order_refs(at_risk),
        "rules": {
            "quiet_order_days": "see rules.py QUIET_ORDER_DAYS",
            "due_within_days": due_within_days,
        },
        "warnings": [] if as_of_date == SNAPSHOT else [
            f"Uses order statuses from the {SNAPSHOT} snapshot; other dates are scenarios, not historical or future facts."
        ],
    }


def trace_order(order_id):
    """Expand one order into the source rows and computed facts behind it."""
    found = get_order_status(order_id)
    if found["status"] != "ok":
        return found
    order = found["data"]
    ref = date.fromisoformat(SNAPSHOT)

    facts = {
        "days_since_last_activity": (ref - date.fromisoformat(order["last_activity_date"])).days,
        "risk_reasons": risk_reasons(order, ref),
    }
    if order["status"] == "IN_PROGRESS":
        facts["days_until_due"] = (date.fromisoformat(order["due_date"]) - ref).days
        if order["due_date"] < SNAPSHOT:
            facts["overdue_calendar_days"] = -facts["days_until_due"]
    else:
        facts["days_late_recorded"] = int(order["days_late"])

    evidence = {
        "order": found["source_rows"],
    }
    # 未完成订单再附上它当前工序最近几个工作日的产量记录，作为“是否停滞”的旁证。
    stage_records = []
    if order["status"] == "IN_PROGRESS":
        stage = order["current_stage"]
        records = load_production()
        row_numbers = production_row_numbers()
        for day in previous_workdays(ref, RECENT_WORKDAYS):
            key = day.isoformat()
            match = next((r for r in records
                          if r["stage"] == stage and r["date"] == key), None)
            if match:
                stage_records.append({
                    "date": key,
                    "stage": stage,
                    "pieces_completed": int(match["pieces_completed"]),
                    "source_row": row_numbers[(key, stage)],
                })
    evidence["recent_stage_output"] = stage_records

    return {
        "status": "ok",
        "data": order,
        "facts": facts,
        "evidence": evidence,
        "snapshot_date": SNAPSHOT,
        "source": ORDERS_SOURCE,
        "message": "All facts above are computed from the cited rows; recent stage output is factory-wide context, not per-order progress.",
    }
