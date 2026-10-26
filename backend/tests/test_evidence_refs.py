"""Every shape of citation in tool results becomes one {source, row, key} ref to a real CSV line."""

import csv
from pathlib import Path

import evidence_refs
from production_optimizer import optimize_orders_outsourced
from tools import trace_order

DATA = Path(__file__).resolve().parents[1] / "track1" / "data"


def lines(name):
    with (DATA / name).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.reader(handle))


def test_multi_order_plans_cite_their_orders_and_workshops():
    plan = optimize_orders_outsourced("original_order_pieces", scope="all")
    refs = evidence_refs.collect(plan)
    orders = {r["key"]: r["row"] for r in refs if r["source"].endswith("orders.csv")}
    workshops = {r["key"] for r in refs if r["source"].endswith("workshops.csv")}
    assert set(orders) == {o["order_id"] for o in plan["orders"]}
    assert workshops == {w["workshop_id"] for w in plan["workshops"]}
    # Each ref points at the line holding that order, with the pieces the plan used.
    table = lines("orders.csv")
    for order in plan["orders"]:
        row = dict(zip(table[0], table[orders[order["order_id"]] - 1]))
        assert row["order_id"] == order["order_id"] and int(row["pieces"]) == order["pieces"]


def test_only_records_with_data_are_cited():
    assert evidence_refs.collect({"payload": {"order_id": "ORD-002", "text": "Call the buyer"}}) == []
    assert evidence_refs.collect({"order_id": "ORD-999", "pieces": 5}) == []
    assert evidence_refs.collect({"workshop_id": "W99", "pieces": 5}) == []
    assert evidence_refs.collect({"order_id": ["ORD-002"], "pieces": 5}) == []


def test_order_trace_refs_are_deduplicated():
    refs = evidence_refs.collect(trace_order("ORD-002"))
    keys = [(r["source"], r["row"]) for r in refs]
    assert len(keys) == len(set(keys)) == 4  # the order row and three WASHING output rows
    assert ("track1/data/orders.csv", 86) in keys


def test_evidence_ids_round_trip():
    found = evidence_refs.lookup("workshops.csv", 9)
    assert found["id"] == evidence_refs.evidence_id(found["source"], 9) == "workshops.csv:9"
    assert found["data"]["workshop_id"] == lines("workshops.csv")[8][0] == "W8"
    assert evidence_refs.lookup("workshops.csv", 1) is None  # the header is not a data row
    assert evidence_refs.lookup("orders.csv", 122) is None
    assert evidence_refs.lookup("../config.py", 2) is None
