"""The source rows behind tool results, in one shape, plus the raw CSV rows they point to.

Tools cite their rows in several shapes (see issue B-2): {source, row, key} references,
`source_row` numbers on production or order records, copied production records, workshop entries
and order entries in multi-order plans (an order ID with its pieces). collect() turns all of them
into {source, row, key}; raw_rows() reads the rows so the evidence drawer can show them exactly as
they appear in the CSV.
"""

import csv
from functools import lru_cache
from pathlib import Path

from paths import source_path
from rules import current_version
from data_loader import (ORDERS_SOURCE, PRODUCTION_SOURCE, WORKSHOPS_SOURCE, order_row_numbers,
                         production_row_numbers, scripted_changes, workshop_row_numbers)

_SOURCES = {ORDERS_SOURCE, PRODUCTION_SOURCE, WORKSHOPS_SOURCE}
_BY_FILE = {Path(source).name: source for source in _SOURCES}


def _ref(node):
    """The citation one dict stands for, or None."""
    if isinstance(node.get("source"), str) and isinstance(node.get("row"), int):
        if node["source"] in _SOURCES:
            return node["source"], node["row"], str(node.get("key", ""))
        return None
    if isinstance(node.get("source_row"), int):
        if "order_id" in node and "stage" not in node:
            return ORDERS_SOURCE, node["source_row"], node["order_id"]
        if "date" in node and "stage" in node:
            return PRODUCTION_SOURCE, node["source_row"], f"{node['date']} {node['stage']}"
    if {"date", "stage", "pieces_completed"} <= set(node) and "source_row" not in node:
        row = production_row_numbers().get((node["date"], node["stage"]))
        if row:
            return PRODUCTION_SOURCE, row, f"{node['date']} {node['stage']}"
    if {"order_id", "pieces"} <= set(node) and isinstance(node["order_id"], str):
        # An order a plan or listing used, with the quantity read from its row.
        row = order_row_numbers().get(node["order_id"])
        if row:
            return ORDERS_SOURCE, row, node["order_id"]
    if isinstance(node.get("workshop_id"), str):
        # A workshop profile, estimate or plan allocation: its capacity, cost and lead time come from this row.
        row = workshop_row_numbers().get(node["workshop_id"])
        if row:
            return WORKSHOPS_SOURCE, row, node["workshop_id"]
    return None


def collect(node):
    """Every citation in a tool result, deduplicated, in the order first seen; `id` is what
    GET /evidence/{id} resolves."""
    seen, refs = set(), []

    def walk(value):
        if isinstance(value, dict):
            ref = _ref(value)
            if ref and ref[:2] not in seen:
                seen.add(ref[:2])
                refs.append({"source": ref[0], "row": ref[1], "key": ref[2], "id": evidence_id(ref[0], ref[1])})
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(node)
    return refs


def _table(source):
    # Keyed by the file's modification time and size, so an updated CSV is read again (evaluation Q18).
    stat = source_path(source).stat()
    return _read_table(source, stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=8)
def _read_table(source, mtime_ns, size):
    with source_path(source).open(encoding="utf-8-sig", newline="") as handle:
        return tuple(csv.reader(handle))


def with_snapshot(source, data):
    """An orders.csv row as the app sees it now: a scripted snapshot's changes are applied and named, so
    the evidence matches the answer while saying which values are simulated."""
    version = current_version()
    change = scripted_changes(version).get(data.get("order_id")) if source == ORDERS_SOURCE else None
    if not change:
        return data
    return {**data, **change, "scripted_change": f"{', '.join(change)} from snapshot {version} "
                                                "(track1/scenarios/watch_snapshots.json)"}


def raw_rows(refs):
    """{"<source>#<row>": {column: value}} for each citation; row is the file line (header = 1)."""
    rows = {}
    for ref in refs:
        table = _table(ref["source"])
        if 2 <= ref["row"] <= len(table):
            rows[f"{ref['source']}#{ref['row']}"] = with_snapshot(ref["source"], dict(zip(table[0], table[ref["row"] - 1])))
    return rows


def evidence_id(source, row):
    """The short ID that GET /evidence/{id} resolves: file name and line, e.g. "orders.csv:12"."""
    return f"{Path(source).name}:{row}"


def lookup(file_name, row):
    """One data row of a source file as {id, source, row, data}, or None if there is no such row."""
    source = _BY_FILE.get(file_name)
    if source is None:
        return None
    data = raw_rows([{"source": source, "row": row}]).get(f"{source}#{row}")
    return None if data is None else {"id": evidence_id(source, row), "source": source, "row": row, "data": data}
