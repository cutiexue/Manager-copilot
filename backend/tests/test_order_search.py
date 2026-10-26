"""Order search behind the reminder dialog: matching, ranking and result caps."""

import pytest

from order_search import search_orders


def ids(result):
    return [order["order_id"] for order in result["orders"]]


def test_empty_query_lists_unfinished_orders_at_risk_first():
    result = search_orders("")
    assert (result["total"], result["count"]) == (34, 8)
    assert ids(result)[:2] == ["ORD-107", "ORD-120"]
    assert all(order["status"] == "IN_PROGRESS" and order["risk_reasons"] for order in result["orders"])


@pytest.mark.parametrize("query", ["ORD-107", "ord-107", "ord107", "107"])
def test_order_id_in_any_spelling(query):
    result = search_orders(query)
    assert ids(result)[0] == "ORD-107"
    assert result["orders"][0]["source_row"] == 81


def test_partial_customer_name_finds_all_its_orders_unfinished_first():
    result = search_orders("maple", limit=50)
    assert result["total"] == 19
    assert {order["customer"] for order in result["orders"]} == {"Maple & Co"}
    assert ids(result)[:2] == ["ORD-083", "ORD-093"]
    assert result["orders"][2]["status"] == "COMPLETE"


def test_every_word_must_match():
    assert search_orders("hoodie")["total"] == 26
    combined = search_orders("maple hoodie", limit=50)
    assert combined["total"] == 7
    assert {(o["customer"], o["product"]) for o in combined["orders"]} == {("Maple & Co", "Hoodie")}


def test_no_match_and_caps():
    assert search_orders("zzz")["total"] == 0
    assert search_orders("hoodie", limit=3)["count"] == 3
    assert search_orders("x" * 201)["status"] == "error"
    assert search_orders("", limit=0)["status"] == "error"
    assert search_orders("", limit=51)["status"] == "error"
