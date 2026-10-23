"""query_orders, conversation order selection and multi-order plans (added 2026-10-22)."""

import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from order_selection import selection_context
from plan_context import get_current_plan, plan_context, revise_order_plan
from production_optimizer import optimize_orders_cheapest, optimize_orders_outsourced
from tools import query_orders


def test_query_orders_totals():
    result = query_orders()
    assert (result["count"], result["original_order_pieces"]) == (120, 93500)
    assert {k: v["order_count"] for k, v in result["by_status"].items()} == {
        "COMPLETE": 86, "IN_PROGRESS": 34}

    unfinished = query_orders(status="IN_PROGRESS")
    assert (unfinished["count"], unfinished["original_order_pieces"]) == (34, 32850)
    assert {k: (v["order_count"], v["original_order_pieces"])
            for k, v in unfinished["by_category"].items()} == {
        "TOPS": (22, 20450), "ACCESSORIES": (12, 12400)}


def test_query_orders_refuses_partial_totals():
    assert query_orders(order_ids=["ORD-002", "ORD-999"])["status"] == "not_found_ids"


def test_selected_scope_needs_a_previous_query():
    # 没有上一轮查询时，“这些订单”不能悄悄变成全部订单。
    assert query_orders(scope="selected")["status"] == "needs_clarification"


def test_selection_is_rebuilt_from_saved_tool_results():
    first = query_orders(status="IN_PROGRESS")
    saved = [HumanMessage(content="How many unfinished orders?"),
             AIMessage(content="", tool_calls=[{"name": "query_orders", "args": {}, "id": "c1"}]),
             ToolMessage(content=json.dumps(first), name="query_orders", tool_call_id="c1"),
             AIMessage(content="34.")]
    with selection_context(saved):
        tops = query_orders(scope="selected", category="TOPS")
    assert (tops["count"], tops["original_order_pieces"]) == (22, 20450)


def test_order_plan_scope_check_and_result():
    ids = ["ORD-002", "ORD-120"]
    assert optimize_orders_outsourced("original_order_pieces", scope="all", order_ids=ids,
                                      expected_order_count=3)["status"] == "scope_mismatch"
    fastest = optimize_orders_outsourced("original_order_pieces", scope="all", order_ids=ids)
    assert (fastest["status"], fastest["total_pieces"], fastest["completion_date"]) == (
        "ok", 2500, "2026-04-09")
    cheapest = optimize_orders_cheapest("original_order_pieces", 30, scope="all", order_ids=ids)
    assert cheapest["status"] == "ok"
    assert cheapest["external_processing_cost"] <= fastest["external_processing_cost"]


def test_plan_revision_needs_a_saved_plan():
    with plan_context([]):
        assert get_current_plan()["status"] == "needs_clarification"
        assert revise_order_plan(5, "completion_date")["status"] == "needs_clarification"
