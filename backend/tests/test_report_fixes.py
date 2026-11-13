"""Fixes for the failures in the team's evaluation report (Evaluation.pdf, F04 and F11-F13)."""

import json

from langchain_core.messages import AIMessage

import skills
from answer_check import check
from llm import execute_tool
from tests.test_chat_actions import call, make
from tool_schemas import TOOLS


def run(name, **args):
    return execute_tool(name, json.dumps(args))


def test_f11_every_tops_workshop_is_listed_with_its_status_and_row():
    # Q08 named four workshops; the CSV has seven that make TOPS, six of them active.
    tops = run("list_workshops", category="TOPS")
    assert tops["status"] == "ok"
    assert tops["workshop_ids"] == ["W1", "W2", "W3", "W5", "W6", "W7", "W8"]
    assert (tops["count"], tops["active_count"]) == (7, 6)
    assert next(w for w in tops["data"] if w["workshop_id"] == "W7")["status"] == "SUSPENDED"
    assert [ref["row"] for ref in tops["source_rows"]] == [2, 3, 4, 6, 7, 8, 9]
    active = run("list_workshops", category="TOPS", status="ACTIVE")
    assert active["workshop_ids"] == ["W1", "W2", "W3", "W5", "W6", "W8"]
    assert run("list_workshops")["count"] == 8
    assert run("list_workshops", category="SHOES")["status"] == "error"


def test_f11_catalog_questions_are_routed_to_the_list_tool():
    feasibility = next(skill for skill in skills.SKILLS if skill["name"] == "feasibility")
    assert "list_workshops" in feasibility["tools"]
    assert "which workshops can make what" in feasibility["when"]
    assert "list_workshops" in feasibility["rules"]


def test_f04_customers_with_two_or_more_overdue_orders_are_counted_by_the_tool():
    overdue = run("get_overdue_orders")
    several = overdue["customers_with_two_or_more"]
    assert several == {"count": 4, "customers": ["Cotton Club", "Maple & Co", "Northwind Apparel", "TrendCart"]}
    groups = {group["customer"]: sorted(group["order_ids"]) for group in overdue["by_customer"]}
    assert groups["Northwind Apparel"] == ["ORD-107", "ORD-114"]
    assert sum(group["count"] for group in overdue["by_customer"]) == overdue["count"] == 8


def test_f13_each_northwind_order_carries_its_own_overdue_days():
    customer = run("get_customer_orders", customer="Northwind Apparel")
    days = {o["order_id"]: o["overdue_calendar_days"] for o in customer["data"] if o["status"] == "IN_PROGRESS"}
    assert days == {"ORD-107": 16, "ORD-114": 9, "ORD-099": 0, "ORD-029": 0, "ORD-066": 0}
    found = {o["order_id"]: o["overdue_calendar_days"] for o in run("search_orders", query="Northwind")["orders"]}
    assert (found["ORD-107"], found["ORD-114"]) == (16, 9)


def test_f13_an_overdue_figure_on_the_wrong_order_is_flagged():
    customer = run("get_customer_orders", customer="Northwind Apparel")
    wrong = check("Which one? ORD-107 (Cardigan) is 9 days overdue; ORD-114 (Hoodie) is 9 days overdue.", [customer])
    assert wrong["unverified"] == [{"kind": "attribution", "text": "ORD-107: 9 days overdue"}]
    right = check("ORD-107 is overdue by 16 calendar days.\nORD-114 is 9 days late.", [customer])
    assert right["unverified"] == []
    assert check("ORD-107 逾期9天。", [customer])["unverified"] == [{"kind": "attribution", "text": "ORD-107: 9 days overdue"}]
    # An order with no overdue figure in the tool results is not judged.
    assert check("ORD-107 is 9 days overdue.", [{"order_id": "ORD-107", "due_date": "2026-03-16"}])["unverified"] == []


def test_f13_a_misattributed_answer_is_answered_again_once(tmp_path):
    script = [call("get_customer_orders", {"customer": "Northwind Apparel"}, "c1"),
              AIMessage(content="Which order? ORD-107 is 9 days overdue."),
              call("get_customer_orders", {"customer": "Northwind Apparel"}, "c2"),
              AIMessage(content="Which order? ORD-107 is 16 days overdue and ORD-114 is 9 days overdue.")]
    service, client = make(tmp_path, script)
    session = client.post("/sessions", json={"title": "t"}).json()["id"]
    reply = client.post(f"/sessions/{session}/messages", json={"message": "Pull up the Northwind order"}).json()
    assert reply["answer_check"]["retried"] is True
    assert reply["answer_check"]["unverified"] == []
    assert reply["answer"].startswith("Which order? ORD-107 is 16 days")
    assert "is 9 days overdue." not in str(service.store.get_history(session)).split("ORD-114")[0]


def test_f12_a_stated_today_moves_yesterday():
    policy = next(skill for skill in skills.SKILLS if skill["name"] == "base_grounding_policy")["rules"]
    assert "states a different today" in policy and "even a Sunday" in policy
    stage = next(t for t in TOOLS if t["function"]["name"] == "get_stage_output")
    assert "count back from that day" in stage["function"]["parameters"]["properties"]["production_date"]["description"]
    # The tools themselves already answer the Q43 dates.
    sunday = run("get_stage_output", stage="ASSEMBLY", production_date="2026-03-29")
    saturday = run("get_stage_output", stage="ASSEMBLY", production_date="2026-03-28")
    assert (sunday["data"]["pieces_completed"], saturday["data"]["pieces_completed"]) == (0, 445)
