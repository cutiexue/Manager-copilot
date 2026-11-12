"""answer_check: figures, dates and order IDs in an answer must come from the turn's tool results."""

import json

import pytest
from langchain_core.messages import AIMessage

from answer_check import check
from llm import execute_tool
from period_output import summarize_stage_output
from tests.test_chat_actions import call, make

MARCH = [summarize_stage_output("2026-03-01", "2026-03-31", "ASSEMBLY")]


def test_correct_figures_pass_whatever_their_format():
    result = check("Assembly made 18,326 pieces in March over 26 workdays: about 704.8 per workday.", MARCH)
    assert result == {"checked": 3, "unverified": []}


def test_the_v1_report_wrong_totals_are_caught():
    result = check("Assembly made 20,486 pieces, approximately 660 per working day.", MARCH)
    assert [u["text"] for u in result["unverified"]] == ["20,486", "660"]


def test_percentages_rates_and_signs_match_by_value():
    compare = execute_tool("compare_stage_output", json.dumps({"stage": "ASSEMBLY", "production_date": "2026-03-31"}))
    assert check("455 pieces on 31 Mar, 11.8% below the 515.7 average.", [compare])["unverified"] == []
    risk = {"workshops": [{"rework_chance": 0.09}]}
    assert check("BudgetWorks has a 9% chance of rework.", [risk])["unverified"] == []


def test_invented_orders_and_dates_are_caught():
    overdue = execute_tool("get_overdue_orders", "{}")
    result = check("ORD-107 was due 2026-03-16 and ORD-999 on 2 March.", [overdue])
    assert {(u["kind"], u["text"]) for u in result["unverified"]} == {("order", "ORD-999"), ("date", "2026-03-02")}


def test_small_counts_years_times_and_list_numbers_are_not_checked():
    result = check("1. Two orders in 2026.\n2. Remind me at 09:00, 3 items.", [])
    assert result == {"checked": 0, "unverified": []}


def test_the_manager_s_own_numbers_count_as_known():
    assert check("For 800 pieces by 25 April, yes.", [], question="Can we make 800 by 25 April?")["unverified"] == []


def test_every_chat_answer_carries_its_check(tmp_path):
    script = [call("get_order_status", {"order_id": "ORD-107"}, "c1"),
              AIMessage(content="ORD-107 has 2000 pieces and is 99 days late.")]
    _, client = make(tmp_path, script)
    session = client.post("/sessions", json={"title": "t"}).json()["id"]
    reply = client.post(f"/sessions/{session}/messages", json={"message": "Check ORD-107"}).json()
    assert reply["answer_check"]["unverified"] == [{"kind": "number", "text": "99"}]
    assert reply["answer_check"]["retried"] is False  # a tool was called, so no second attempt
    [_, answer] = client.get(f"/sessions/{session}/messages").json()
    assert answer["answer_check"]["unverified"] == reply["answer_check"]["unverified"]  # also in the history


def test_day_ranges_are_dates_not_figures():
    known = [{"days": ["2026-03-27", "2026-03-31", "2026-03-28"]}]
    assert check("Output over 27–31 March and March 28-31 fell.", known)["unverified"] == []


def test_orders_from_earlier_turns_may_be_named_but_their_figures_must_be_fresh():
    earlier = [{"order_id": "ORD-114", "pieces": 2000}]
    assert check("The ORD-114 draft is waiting for Confirm.", [], earlier_results=earlier)["unverified"] == []
    result = check("ORD-114 has 2,000 pieces.", [], earlier_results=earlier)
    assert result["unverified"] == [{"kind": "number", "text": "2,000"}]


def test_words_that_start_like_months_are_not_dates():
    compare = execute_tool("compare_stage_output", json.dumps({"stage": "ASSEMBLY", "production_date": "2026-03-31"}))
    for answer in ("Assembly output decreased 11.8% against the 515.7 baseline.",
                   "12 may need a call today.", "I marked 12 orders.", "Output declined 12% this week.",
                   "There are 12 separate orders."):
        assert not [u for u in check(answer, [compare, {"count": 12}])["unverified"] if u["kind"] == "date"], answer
    # Real month names and abbreviations are still dates.
    dates = {u["text"] for u in check("Due 31 Mar, 12 May, Dec 12 and sept 3.", [])["unverified"]}
    assert dates == {"2026-03-31", "2026-05-12", "2026-12-12", "2026-09-03"}


def test_figures_in_chinese_answers_are_checked():
    lookup = [{"order_id": "ORD-107", "pieces": 2000, "days_late": 16, "due_date": "2026-03-16", "count": 12}]
    assert check("订单ORD-107已逾期16天，共2000件，截止2026-03-16。", lookup) == {"checked": 4, "unverified": []}
    assert check("共有99个订单存在风险。", lookup)["unverified"] == [{"kind": "number", "text": "99"}]


def test_a_source_row_number_vouches_only_for_a_row_citation():
    lookup = [{"order_id": "ORD-083", "source_rows": [{"source": "track1/data/orders.csv", "row": 88,
                                                        "key": "ORD-083"}], "count": 12}]
    assert check("ORD-083 is on row 88 of orders.csv.", lookup)["unverified"] == []
    assert check("ORD-083 在 orders.csv 第88行。", lookup)["unverified"] == []
    assert check("88 orders are at risk.", lookup)["unverified"] == [{"kind": "number", "text": "88"}]


@pytest.mark.parametrize("answer", [
    "Evidence: row 88. There are 88 overdue orders.",
    "There are 88 overdue orders. Evidence: row 88.",
    "共有88个逾期订单，证据在第88行。",
    "证据在第88行，共有88个逾期订单。",
    "ORD-083 was due 2026-03-16. Row 88 reports 88 overdue orders.",
])
def test_a_row_citation_does_not_vouch_for_another_mention_of_the_same_number(answer):
    lookup = [{"order_id": "ORD-083", "due_date": "2026-03-16", "row": 88, "count": 12}]
    result = check(answer, lookup)
    assert result["unverified"] == [{"kind": "number", "text": "88"}]
    assert result["checked"] == (4 if answer.startswith("ORD-") else 2)


@pytest.mark.parametrize("answer", [
    "第88个订单存在风险。",
    "请查看第88个订单，证据在第88行。",
    "证据在第88行，请查看第88个订单。",
])
def test_a_chinese_ordinal_is_not_a_row_citation(answer):
    assert check(answer, [{"row": 88}])["unverified"] == [{"kind": "number", "text": "88"}]


@pytest.mark.parametrize("citation", ["row 88", "row #88", "line no. 88", "#88", "第88行", "第 88 行"])
def test_real_row_citations_are_still_verified(citation):
    answer = f"ORD-083 was due 2026-03-16; evidence: {citation}."
    lookup = [{"order_id": "ORD-083", "due_date": "2026-03-16", "source_row": 88}]
    assert check(answer, lookup) == {"checked": 3, "unverified": []}


def test_a_row_citation_does_not_exempt_a_percentage_or_decimal():
    assert check("Row 88: 88% are late, by 88.5 days.", [{"row": 88}])["unverified"] == [
        {"kind": "number", "text": "88%"}, {"kind": "number", "text": "88.5"},
    ]


def test_a_repeated_number_is_valid_if_also_supported_as_a_fact():
    assert check("Row 88 reports 88 overdue orders.", [{"row": 88, "count": 88}]) == {
        "checked": 2, "unverified": [],
    }


def test_figures_without_any_lookup_are_answered_again_after_a_lookup(tmp_path):
    script = [call("get_overdue_orders", {}, "c1"), AIMessage(content="8 orders are overdue."),
              AIMessage(content="Those two total 1,800 pieces."),  # from memory: no tool this turn
              call("query_orders", {"scope": "all", "customer": "Cotton Club", "status": "IN_PROGRESS"}, "c2"),
              AIMessage(content="Cotton Club has open orders.")]
    service, client = make(tmp_path, script)
    session = client.post("/sessions", json={"title": "t"}).json()["id"]
    client.post(f"/sessions/{session}/messages", json={"message": "Which orders are overdue?"})
    reply = client.post(f"/sessions/{session}/messages", json={"message": "How many pieces is that?"}).json()
    assert reply["answer_check"]["retried"] is True
    assert [c["name"] for c in reply["tool_calls"]] == ["query_orders"]
    assert reply["answer"] == "Cotton Club has open orders."
    stored = service.store.get_history(session)
    assert "1,800" not in str(stored)  # the first, unchecked draft is not kept
