"""Provide tools for querying factory data."""

from datetime import date, timedelta

from data_loader import load_orders, load_production


def get_order_status(order_id):
    """Return the matching order or a not_found result."""
    # 读取全部订单。
    orders = load_orders()

    # 按订单编号精确匹配。
    for order in orders:
        if order["order_id"] == order_id:
            return {"status": "ok", "data": order}

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
        return {"status": "ok", "count": len(matched_orders), "data": matched_orders}

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
            return {
                "status": "ok",
                "data": result,
                "source": "track1/data/production_log.csv",
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
    baseline_dates = []
    previous_date = target_date - timedelta(days=1)
    while len(baseline_dates) < baseline_days:
        if previous_date.weekday() != 6:
            baseline_dates.append(previous_date.isoformat())
        previous_date -= timedelta(days=1)

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
        "warnings": ["A historical comparison is not an anomaly diagnosis or a forecast."],
    }


def get_overdue_orders(as_of_date="2026-04-01"):
    """Find unfinished orders past their due date using the stored snapshot."""
    # 把日期文本转换成日期对象，才能比较日期和计算天数。
    try:
        reference_date = date.fromisoformat(as_of_date)
    except (TypeError, ValueError):
        return {"status": "error", "message": "Use a valid date in YYYY-MM-DD format."}

    overdue_orders = []
    for order in load_orders():
        due_date = date.fromisoformat(order["due_date"])
        if order["status"] == "IN_PROGRESS" and due_date < reference_date:
            # 复制到内存里的新字典，再添加计算结果；不改原始记录或文件。
            result = order.copy()
            result["overdue_calendar_days"] = (reference_date - due_date).days
            overdue_orders.append(result)

    return {
        "status": "ok",
        "as_of_date": reference_date.isoformat(),
        "snapshot_date": "2026-04-01",
        "count": len(overdue_orders),
        "data": overdue_orders,
        "source": "track1/data/orders.csv",
        "warnings": [] if as_of_date == "2026-04-01" else [
            "Uses order statuses from the 2026-04-01 snapshot; other dates are scenarios, not historical or future facts."
        ],
    }
