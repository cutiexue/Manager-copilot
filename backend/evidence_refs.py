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


def _ref(node, resolve_implicit=True):
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
    if not resolve_implicit:
        return None
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


def collect(node, *, versioned=False, resolve_implicit=True):
    """Every citation in a tool result, deduplicated, in the order first seen; `id` is what
    GET /evidence/{id} resolves. Versioned refs preserve distinct snapshots of the same row.

    Explicit data_version on a reference or parent object overrides the request's
    snapshot, e.g. a feasibility calculation's original-course workload (v0).
    """
    seen, refs = set(), []

    def walk(value, inherited_version=None):
        if isinstance(value, dict):
            selected_version = value.get("data_version", inherited_version)
            ref = _ref(value, resolve_implicit)
            pinned = selected_version or (current_version() if versioned else None)
            identity = (*ref[:2], pinned) if ref else None
            if ref and identity not in seen:
                seen.add(identity)
                item = {"source": ref[0], "row": ref[1], "key": ref[2],
                        "id": evidence_id(ref[0], ref[1], pinned)}
                if pinned is not None:
                    item.update(data_version=pinned, row_key=f"{ref[0]}#{ref[1]}@{pinned}")
                refs.append(item)
            for child in value.values():
                walk(child, selected_version)
        elif isinstance(value, list):
            for child in value:
                walk(child, inherited_version)

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


def with_snapshot(source, data, version=None):
    """An orders.csv row as the app sees it now: a scripted snapshot's changes are applied and named, so
    the evidence matches the answer while saying which values are simulated."""
    version = version or current_version()
    change = scripted_changes(version).get(data.get("order_id")) if source == ORDERS_SOURCE else None
    if not change:
        return data
    return {**data, **change, "scripted_change": f"{', '.join(change)} from snapshot {version} "
                                                "(track1/scenarios/watch_snapshots.json)"}


def raw_rows(refs):
    """Raw rows keyed by row_key (versioned refs) or source#line (legacy refs)."""
    rows = {}
    for ref in refs:
        table = _table(ref["source"])
        if 2 <= ref["row"] <= len(table):
            key = ref.get("row_key", f"{ref['source']}#{ref['row']}")
            rows[key] = with_snapshot(ref["source"], dict(zip(table[0], table[ref["row"] - 1])),
                                      ref.get("data_version"))
    return rows


def evidence_id(source, row, version=None):
    """A source row, optionally pinned, e.g. orders.csv:12@v0. Old IDs remain supported."""
    return f"{Path(source).name}:{row}" + (f"@{version}" if version is not None else "")


def lookup(file_name, row, version=None):
    """One data row of a source file as {id, source, row, data}, or None if there is no such row."""
    source = _BY_FILE.get(file_name)
    if source is None:
        return None
    if version is not None:
        # Validate even non-orders refs, so an unknown version is never silently accepted.
        scripted_changes(version)
    ref = {"source": source, "row": row}
    if version is not None:
        ref.update(data_version=version, row_key=f"{source}#{row}@{version}")
    data = raw_rows([ref]).get(ref.get("row_key", f"{source}#{row}"))
    result = None if data is None else {"id": evidence_id(source, row, version), "source": source,
                                      "row": row, "data": data}
    if result is not None and version is not None:
        result["data_version"] = version
    return result
