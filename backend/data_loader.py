"""Load and validate order data for Track 1."""

import csv
from math import isfinite
from datetime import date
from pathlib import Path


# 根据代码文件定位数据，不依赖运行命令时所在的目录。
DATA_DIR = Path(__file__).resolve().parent / "track1" / "data"

ORDERS_FILE = "orders.csv"
PRODUCTION_FILE = "production_log.csv"
WORKSHOPS_FILE = "workshops.csv"

ORDERS_SOURCE = f"track1/data/{ORDERS_FILE}"
PRODUCTION_SOURCE = f"track1/data/{PRODUCTION_FILE}"
WORKSHOPS_SOURCE = f"track1/data/{WORKSHOPS_FILE}"

STAGES = ("KNITTING", "ASSEMBLY", "WASHING", "PACKING")
CATEGORIES = ("TOPS", "ACCESSORIES")
ORDER_STATUSES = ("COMPLETE", "IN_PROGRESS")
WORKSHOP_STATUSES = ("ACTIVE", "SUSPENDED")


class DataValidationError(ValueError):
    """Raised when a source CSV violates the data dictionary."""


def _read_csv(filename):
    """Read CSV rows, preserving strings and empty strings."""
    file_path = DATA_DIR / filename
    # 原始数据只读；清洗结果或新增数据必须保存到其他目录。
    with file_path.open(mode="r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def _fail(filename, row_number, message):
    """Report a validation problem with its CSV line number (header is line 1)."""
    raise DataValidationError(f"{filename} row {row_number}: {message}")


def _require_columns(filename, rows, required):
    missing = [column for column in required if column not in rows[0]]
    if missing:
        raise DataValidationError(f"{filename}: missing columns: {', '.join(missing)}.")
    for index, row in enumerate(rows, 2):
        if None in row or any(row.get(column) is None for column in required):
            _fail(filename, index, "CSV row has missing or extra cells.")


def _parse_date(filename, row_number, row, column):
    try:
        return date.fromisoformat(row[column])
    except (TypeError, ValueError):
        _fail(filename, row_number, f"{column} must be a valid YYYY-MM-DD date, got {row[column]!r}.")


def _parse_int(filename, row_number, row, column, minimum=None):
    try:
        value = int(row[column])
    except (TypeError, ValueError):
        _fail(filename, row_number, f"{column} must be an integer, got {row[column]!r}.")
    if minimum is not None and value < minimum:
        _fail(filename, row_number, f"{column} must be at least {minimum}, got {value}.")
    return value


def _parse_float(filename, row_number, row, column, minimum=None, maximum=None):
    try:
        value = float(row[column])
    except (TypeError, ValueError):
        _fail(filename, row_number, f"{column} must be a number, got {row[column]!r}.")
    if not isfinite(value):
        _fail(filename, row_number, f"{column} must be finite.")
    if minimum is not None and value < minimum:
        _fail(filename, row_number, f"{column} must be at least {minimum}, got {value}.")
    if maximum is not None and value > maximum:
        _fail(filename, row_number, f"{column} must be at most {maximum}, got {value}.")
    return value


def _validate_orders(filename, rows):
    _require_columns(filename, rows, (
        "order_id", "customer", "product", "category", "pieces", "order_date",
        "due_date", "status", "current_stage", "last_activity_date",
        "completed_date", "days_late",
    ))
    seen_ids = set()
    for index, row in enumerate(rows):
        row_number = index + 2
        order_id = row["order_id"].strip()
        if not order_id:
            _fail(filename, row_number, "order_id cannot be empty.")
        if order_id in seen_ids:
            _fail(filename, row_number, f"duplicate order_id {order_id!r}.")
        seen_ids.add(order_id)
        if row["category"] not in CATEGORIES:
            _fail(filename, row_number, f"category must be one of {CATEGORIES}, got {row['category']!r}.")
        _parse_int(filename, row_number, row, "pieces", minimum=1)
        _parse_date(filename, row_number, row, "order_date")
        _parse_date(filename, row_number, row, "due_date")
        _parse_date(filename, row_number, row, "last_activity_date")
        if row["status"] not in ORDER_STATUSES:
            _fail(filename, row_number, f"status must be one of {ORDER_STATUSES}, got {row['status']!r}.")
        if row["current_stage"] not in STAGES + ("COMPLETE",):
            _fail(filename, row_number, f"unknown current_stage {row['current_stage']!r}.")
        if row["status"] == "COMPLETE":
            _parse_date(filename, row_number, row, "completed_date")
            _parse_int(filename, row_number, row, "days_late")
        elif row["completed_date"] or row["days_late"]:
            _fail(filename, row_number, "IN_PROGRESS orders must leave completed_date and days_late blank.")


def _validate_production(filename, rows):
    _require_columns(filename, rows, ("date", "stage", "pieces_completed"))
    seen_pairs = set()
    for index, row in enumerate(rows):
        row_number = index + 2
        _parse_date(filename, row_number, row, "date")
        if row["stage"] not in STAGES:
            _fail(filename, row_number, f"stage must be one of {STAGES}, got {row['stage']!r}.")
        _parse_int(filename, row_number, row, "pieces_completed", minimum=0)
        pair = (row["date"], row["stage"])
        if pair in seen_pairs:
            _fail(filename, row_number, f"duplicate record for {row['stage']} on {row['date']}.")
        seen_pairs.add(pair)


def _validate_workshops(filename, rows):
    _require_columns(filename, rows, (
        "workshop_id", "name", "capacity_pieces_per_day", "pickup_lead_days",
        "defect_rate", "cost_per_piece", "makes", "status", "max_batch_pieces",
        "current_queue_days", "notes",
    ))
    seen_ids = set()
    for index, row in enumerate(rows):
        row_number = index + 2
        workshop_id = row["workshop_id"].strip()
        if not workshop_id:
            _fail(filename, row_number, "workshop_id cannot be empty.")
        if workshop_id in seen_ids:
            _fail(filename, row_number, f"duplicate workshop_id {workshop_id!r}.")
        seen_ids.add(workshop_id)
        _parse_float(filename, row_number, row, "capacity_pieces_per_day", minimum=1)
        _parse_int(filename, row_number, row, "pickup_lead_days", minimum=0)
        _parse_float(filename, row_number, row, "defect_rate", minimum=0, maximum=1)
        _parse_float(filename, row_number, row, "cost_per_piece", minimum=0)
        capabilities = row["makes"].split("+")
        if not capabilities or any(part not in CATEGORIES for part in capabilities):
            _fail(filename, row_number, f"makes must combine {CATEGORIES}, got {row['makes']!r}.")
        if row["status"] not in WORKSHOP_STATUSES:
            _fail(filename, row_number, f"status must be one of {WORKSHOP_STATUSES}, got {row['status']!r}.")
        if row["max_batch_pieces"]:
            _parse_int(filename, row_number, row, "max_batch_pieces", minimum=1)
        _parse_float(filename, row_number, row, "current_queue_days", minimum=0)


_VALIDATORS = {
    ORDERS_FILE: _validate_orders,
    PRODUCTION_FILE: _validate_production,
    WORKSHOPS_FILE: _validate_workshops,
}


def _load(filename):
    rows = _read_csv(filename)
    if not rows:
        raise DataValidationError(f"{filename}: no data rows found.")
    _VALIDATORS[filename](filename, rows)
    return rows


def load_orders():
    """Return validated order dictionaries, preserving strings and empty strings."""
    return _load(ORDERS_FILE)


def load_production():
    """Return validated daily production records without modifying the source file."""
    return _load(PRODUCTION_FILE)


def load_workshops():
    """Return validated workshop profiles without modifying the source file."""
    return _load(WORKSHOPS_FILE)


def order_row_numbers():
    """Map order_id to its CSV line number (header is line 1)."""
    return {row["order_id"]: index + 2 for index, row in enumerate(load_orders())}


def production_row_numbers():
    """Map (date, stage) to its CSV line number (header is line 1)."""
    return {(row["date"], row["stage"]): index + 2
            for index, row in enumerate(load_production())}


def workshop_row_numbers():
    """Map workshop_id to its CSV line number (header is line 1)."""
    return {row["workshop_id"]: index + 2 for index, row in enumerate(load_workshops())}


def source_ref(source, row_number, key):
    """Build one source-row citation for a tool result."""
    return {"source": source, "row": row_number, "key": key}
