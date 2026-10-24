"""The source rows behind tool results, in one shape, plus the raw CSV rows they point to.

Tools cite their rows in several shapes (see issue B-2): {source, row, key} references,
`source_row` numbers on production or order records, workshop profiles and copied production
records. collect() turns all of them into {source, row, key}; raw_rows() reads the rows so the
evidence drawer can show them exactly as they appear in the CSV.
"""

import csv
from functools import lru_cache
from pathlib import Path

from data_loader import (ORDERS_SOURCE, PRODUCTION_SOURCE, WORKSHOPS_SOURCE, production_row_numbers,
                         workshop_row_numbers)

BACKEND_DIR = Path(__file__).resolve().parent
_SOURCES = {ORDERS_SOURCE, PRODUCTION_SOURCE, WORKSHOPS_SOURCE}


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
    if {"workshop_id", "capacity_pieces_per_day"} <= set(node):
        row = workshop_row_numbers().get(node["workshop_id"])
        if row:
            return WORKSHOPS_SOURCE, row, node["workshop_id"]
    return None


def collect(node):
    """Every citation in a tool result, deduplicated, in the order first seen."""
    seen, refs = set(), []

    def walk(value):
        if isinstance(value, dict):
            ref = _ref(value)
            if ref and ref[:2] not in seen:
                seen.add(ref[:2])
                refs.append({"source": ref[0], "row": ref[1], "key": ref[2]})
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(node)
    return refs


@lru_cache(maxsize=None)
def _table(source):
    with (BACKEND_DIR / source).open(encoding="utf-8-sig", newline="") as handle:
        return tuple(csv.reader(handle))


def raw_rows(refs):
    """{"<source>#<row>": {column: value}} for each citation; row is the file line (header = 1)."""
    rows = {}
    for ref in refs:
        table = _table(ref["source"])
        if 2 <= ref["row"] <= len(table):
            rows[f"{ref['source']}#{ref['row']}"] = dict(zip(table[0], table[ref["row"] - 1]))
    return rows
