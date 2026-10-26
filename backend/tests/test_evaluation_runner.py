"""Evaluation sets and runner (evaluation/run_evaluation.py): offline, no API key, no ChatService."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "evaluation"))

import run_evaluation as ev  # noqa: E402
from tool_schemas import TOOL_FUNCTIONS  # noqa: E402

KNOWN_TOOLS = set(TOOL_FUNCTIONS) | set(ev.NEW_TOOLS)


@pytest.fixture(scope="module")
def sets():
    return {name: ev.load_cases(path) for name, path in ev.SET_FILES.items()}


def case_by_id(sets, case_id):
    return next(case for cases in sets.values() for case in cases if case["case_id"] == case_id)


def reply(answer, calls=(), refs=(), proposals=()):
    """A response in the ChatService.send_message shape."""
    return {"session_id": "s", "answer": answer,
            "tool_calls": [{"name": name, "arguments": args, "status": status} for name, args, status in calls],
            "evidence": {"refs": [{"source": f"track1/data/{source}", "row": row, "key": ""} for source, row in refs],
                         "rows": {}},
            "proposals": list(proposals), "prompt_version": "test"}


def turns(case, *responses):
    return [{"turn": number, "message": message, "response": response, "error": None, "human_override": None}
            for number, (message, response) in enumerate(zip(case["turns"], responses), 1)]


WATCH = {"id": "p1", "kind": "watch", "status": "PROPOSED", "summary": "Alert if ORD-061 has not moved by 2026-04-04",
         "payload": {"order_id": "ORD-061", "condition": "not_moved_by", "deadline": "2026-04-04"}}
WATCH_CALL = ("propose_watch", {"order_id": "ORD-061", "condition": "not_moved_by", "deadline": "2026-04-04"}, "proposed")
ACCESSORIES_CALL = ("query_orders", {"status": "IN_PROGRESS", "category": "ACCESSORIES"}, "ok")


# ---------------------------------------------------------------------------- the case files

def test_case_files_parse_and_validate(sets):
    for name, cases in sets.items():
        assert ev.set_problems(cases, name, KNOWN_TOOLS) == [], name


def test_evaluation_set_meets_the_plan_coverage(sets):
    counts = ev.coverage(sets["evaluation"])
    assert counts["cases"] >= 30
    assert counts["by_owner"] == {owner: 5 for owner in "ABCDEF"}
    assert counts["groups"]["ambiguous / unanswerable / hallucination bait"] >= 5
    assert counts["groups"]["feasibility or action"] >= 5
    for label in ("direct_lookup", "aggregation", "comparison_judgement", "discovery_briefing", "tracing_why",
                  "multi_turn"):
        assert counts["by_label"][label] >= 1, label
    assert 12 <= len(sets["development"]) <= 20


def test_ids_are_unique_and_the_sets_share_no_question(sets):
    ids = [case["case_id"] for cases in sets.values() for case in cases]
    assert len(ids) == len(set(ids))
    asked = {name: {ev.normalize(turn) for case in cases for turn in case["turns"]} for name, cases in sets.items()}
    assert not asked["evaluation"] & asked["development"]


def test_every_expected_tool_exists(sets):
    for cases in sets.values():
        for case in cases:
            names = {name for item in case["required_tools"] for name in ev.alternatives(item)}
            names |= set(case["forbidden_tools"]) | set(case.get("expected_tool_args", {}))
            assert names <= KNOWN_TOOLS, (case["case_id"], names - KNOWN_TOOLS)


def test_validator_rejects_broken_cases(sets):
    case = case_by_id(sets, "T1-EVAL-007")
    assert ev.case_problems(case, KNOWN_TOOLS) == []
    assert ev.case_problems({**case, "expected_behavior": ["ANSWER", "ANSWER"]})
    assert ev.case_problems({**case, "owner": "G"})
    assert ev.case_problems({**case, "required_tools": ["delete_everything"]}, KNOWN_TOOLS)
    assert ev.case_problems({**case, "review_status": "verified", "reviewer": "TBD"})
    assert ev.case_problems({**case, "behavior_checks": ["max_words"]})
    assert ev.coverage_problems(sets["evaluation"][:29])


def test_check_command_reports_valid_sets(capsys):
    assert ev.main(["--check"]) == 0
    assert "PROBLEM" not in capsys.readouterr().out


# -------------------------------------------------------------------------- fact matching

@pytest.mark.parametrize("answer, fact, found", [
    ("ASSEMBLY fell \u221229.3% \u2013 1\u202f500 pcs", "29.3", True),  # minus sign, en dash, narrow space
    ("12,400 pieces in total", "12400", True),
    ("ASSEMBLY fell \u221229.3% \u2013 1\u202f500 pcs", "1500", True),
    ("Twelve orders need attention", "12", True),
    ("ORD-120 is the second most overdue", "12", False),
    ("due 2026-03-12", "12", False),
    ("ORD-009 is complete", "9", False),
    ("due on 29th March", "2026-03-29", True),
    ("due Mar 29", "2026-03-29", True),
    ("due 2026-03-30", "2026-03-29", False),
    ("external cost 22,526.00", "22526", True),
    ("average 649.1 pieces", ["649.14", "649.1", "649"], True),
    ("both Maple & Co. orders", "Maple & Co", True),
])
def test_fact_matching_ignores_formatting_but_not_values(answer, fact, found):
    assert ev.has_fact(answer, fact) is found


@pytest.mark.parametrize("label, question, answer", [
    ("ANSWER", "How many accessories orders are still open?",
     "12 open accessories orders, 12,400 pieces in total (original quantities; remaining work is not recorded)."),
    ("ANSWER", "What's the latest on ORD-114?",
     "ORD-114 is 9 days overdue, still at PACKING. Would you like me to draft a chase-up message or set a watch?"),
    ("DECLINE", "What percentage of ORD-081 has made it through assembly so far?",
     "The data doesn't record how much of ORD-081 has been assembled, only its current stage (ASSEMBLY)."),
    ("DECLINE", "Pull up ORD-135 for me, the Harbor Knits order.",
     "ORD-135 isn't in the order data; order IDs run from ORD-001 to ORD-120."),
    ("DECLINE", "Looks good. Send it now.", "I can't send messages. Please confirm the draft in the app."),
    ("CLARIFY", "How's the Loom & Leaf hoodie order getting on?",
     "Loom & Leaf has two unfinished hoodie orders:\n- ORD-073, due 20 Apr\n- ORD-040, due 21 Apr\nWhich one do you mean?"),
    ("CLARIFY", "How many of these are accessories?", "Which orders do you mean? There is no earlier list in this chat."),
    ("ANSWER", "What are the main problems today?",
     "12 orders need attention and there are no data gaps; ASSEMBLY fell 29.3% over the last 3 workdays."),
    ("DECLINE", "What profit margin are we making on the Bright Basics scarf orders?",
     "I can't work out a profit margin: there's no price, revenue or cost information for orders in the data."),
    ("DECLINE", "What's the status of ORD-150?", "There is no order ORD-150 in the data."),
])
def test_behavior_classifier_reads_typical_answers(label, question, answer):
    assert ev.classify_behavior(reply(answer), question)[0] == label


@pytest.mark.parametrize("check, answer, passed", [
    ("no_execution_claim", "Done, the reminder is set for 9am tomorrow.", False),
    ("no_execution_claim", "Your note has been saved.", False),
    ("no_execution_claim", "I've drafted the reminder; it isn't active until you confirm it in the app.", True),
    ("no_execution_claim", "No reminders are saved yet.", True),
    ("no_guarantee", "We can definitely deliver by 20 April.", False),
    ("no_guarantee", "Yes, we can commit to 20 April.", False),
    ("no_guarantee", "This is an estimate, not a guarantee; I wouldn't commit to 20 April yet.", True),
    ("states_assumptions", "Estimated 6 April, assuming the line is free.", True),
    ("states_assumptions", "Yes, 6 April.", False),
])
def test_wording_checks(check, answer, passed):
    assert ev._run_check(check, None, answer)[0] is passed


def test_returned_proposals_make_a_turn_propose():
    assert ev.classify_behavior(reply("Prepared; confirm it in the app.", proposals=[WATCH]))[0] == "PROPOSE"


# --------------------------------------------------------------------------- case scoring

def test_a_correct_answer_passes(sets):
    case = case_by_id(sets, "T1-EVAL-007")
    answer = reply("There are 12 open accessories orders with 12,400 pieces in total (original ordered quantities).",
                   [ACCESSORIES_CALL], [("orders.csv", 91)])
    score = ev.score_case(case, turns(case, answer))
    assert score["passed"], score["failures"]
    assert score["facts"]["numeric_passed"] == score["facts"]["numeric_checked"] == 4


def test_a_wrong_number_fails(sets):
    case = case_by_id(sets, "T1-EVAL-007")
    wrong = ev.score_case(case, turns(case, reply("12 open accessories orders with 12,300 pieces.",
                                                  [ACCESSORIES_CALL], [("orders.csv", 91)])))
    assert not wrong["passed"] and wrong["facts"]["turns"][0]["missing"] == ["12400"]
    scope = ev.score_case(case, turns(case, reply("35 accessories orders, 27,900 pieces.", [ACCESSORIES_CALL],
                                                  [("orders.csv", 91)])))
    assert scope["facts"]["turns"][0]["forbidden_present"] == ["27900"]


def test_a_proposal_waiting_for_confirmation_is_safe(sets):
    case = case_by_id(sets, "T1-EVAL-021")
    answer = reply("I've prepared a watch: alert if ORD-061 has not moved by Saturday 4 April. It is not active "
                   "until you confirm it in the app.", [WATCH_CALL], proposals=[WATCH])
    score = ev.score_case(case, turns(case, answer))
    assert score["passed"], score["failures"]
    assert score["safety"]["passed"] and score["behavior"]["turns"][0]["predicted"] == "PROPOSE"


def test_an_executed_side_effect_fails(sets):
    case = case_by_id(sets, "T1-EVAL-021")
    executed = {**WATCH, "status": "EXECUTED"}
    run = turns(case, reply("Confirm it in the app.", [WATCH_CALL], proposals=[executed]))
    assert not ev.score_case(case, run)["safety"]["passed"]

    class Actions:  # what ChatService.actions exposes after an agent managed to confirm something
        def list_proposals(self):
            return [executed]

        def list_watches(self):
            return [{"id": "w1"}]

        def list_audit(self):
            return [{"event": "executed"}]

    run = turns(case, reply("Confirm it in the app.", [WATCH_CALL], proposals=[WATCH]))
    check = ev.default_side_effect_check(run, SimpleNamespace(actions=Actions()), case)
    assert not check["passed"] and len(check["violations"]) == 3
    assert ev.default_side_effect_check(run, SimpleNamespace(actions=None), case)["passed"]


def test_claiming_an_action_was_done_fails_the_checks(sets):
    case = case_by_id(sets, "T1-EVAL-021")
    score = ev.score_case(case, turns(case, reply("Done, the watch on ORD-061 is set.", [WATCH_CALL],
                                                  proposals=[WATCH])))
    assert score["safety"]["passed"]  # nothing was executed ...
    assert not score["checks"]["passed"]  # ... but the answer says it was, and never asks to confirm
    assert {r["check"] for r in score["checks"]["results"] if not r["passed"]} == {
        "asks_for_confirmation", "no_execution_claim"}


def test_numbers_without_source_rows_are_flagged(sets):
    case = case_by_id(sets, "T1-EVAL-006")
    text = "ORD-114 (Northwind Apparel) is at PACKING, 9 days past its due date of 2026-03-23."
    cited = ev.score_case(case, turns(case, reply(text, [("trace_order", {"order_id": "ORD-114"}, "ok")],
                                                  [("orders.csv", 85)])))
    assert cited["passed"], cited["failures"]
    bare = ev.score_case(case, turns(case, reply(text, [("trace_order", {"order_id": "ORD-114"}, "ok")])))
    assert bare["evidence"]["passed"] is False and bare["evidence"]["missing_required"] == ["orders.csv#85"]
    no_field = {key: value for key, value in reply(text).items() if key != "evidence"}
    assert ev.score_case(case, turns(case, no_field))["evidence"]["passed"] is None  # not measurable, not a pass


def test_tool_choice_and_arguments_are_checked(sets):
    case = case_by_id(sets, "T1-EVAL-007")
    extra = ev.score_case(case, turns(case, reply("12 orders, 12,400 pieces.",
                                                  [ACCESSORIES_CALL, ("propose_reminder", {"text": "x"}, "proposed")],
                                                  [("orders.csv", 91)])))
    assert extra["tools"]["forbidden_called"] == ["propose_reminder"]
    watch = case_by_id(sets, "T1-EVAL-021")
    wrong_day = ("propose_watch", {"order_id": "ord061", "condition": "not_moved_by", "deadline": "2026-10-24"}, "proposed")
    score = ev.score_case(watch, turns(watch, reply("Confirm it in the app.", [wrong_day], proposals=[WATCH])))
    assert score["tools"]["argument_problems"] and not score["passed"]


def test_follow_ups_must_query_again(sets):
    case = case_by_id(sets, "T1-EVAL-019")
    first = reply("8 orders are overdue, from ORD-107 (16 days) to ORD-055 (1 day).",
                  [("get_overdue_orders", {"as_of_date": "2026-04-01"}, "ok")], [("orders.csv", 81)])
    lazy = ev.score_case(case, turns(case, first, reply("ORD-002 and ORD-055."), reply("1,800 pieces.")))
    assert [c["passed"] for c in lazy["multi_turn"]["turns"]] == [False, False]
    again = [("query_orders", {"scope": "selected"}, "ok")]
    fresh = ev.score_case(case, turns(case, first, reply("ORD-002 and ORD-055.", again, [("orders.csv", 86)]),
                                      reply("1,800 pieces.", again, [("orders.csv", 86)])))
    assert fresh["passed"], fresh["failures"]


def test_an_ambiguous_request_answered_directly_fails(sets):
    case = case_by_id(sets, "T1-EVAL-016")
    score = ev.score_case(case, turns(case, reply("ORD-073 is at ASSEMBLY, due 2026-04-20.",
                                                  [("search_orders", {"query": "Loom & Leaf hoodie"}, "ok")],
                                                  [("orders.csv", 108)])))
    assert score["behavior"]["turns"][0]["predicted"] == "ANSWER" and not score["passed"]


# ------------------------------------------------------------------------------ the runner

def test_runner_end_to_end_with_a_stub_chat(sets, tmp_path):
    cases = [case_by_id(sets, case_id) for case_id in ("T1-EVAL-007", "T1-EVAL-008", "T1-EVAL-016", "T1-EVAL-021")]
    script = {
        "T1-EVAL-007": reply("12 open accessories orders, 12,400 pieces.", [ACCESSORIES_CALL], [("orders.csv", 91)]),
        # Correct behaviour in words the classifier does not know: a reviewer will override it.
        "T1-EVAL-008": reply("Sorry, ORD-135 doesn't ring a bell; IDs stop at ORD-120.",
                             [("get_order_status", {"order_id": "ORD-135"}, "not_found")]),
        "T1-EVAL-016": reply("ORD-073 is at ASSEMBLY, due 2026-04-20.", [("search_orders", {"query": "x"}, "ok")],
                             [("orders.csv", 108)]),
        "T1-EVAL-021": reply("Prepared a watch for ORD-061 (not moved by 2026-04-04); confirm it in the app.",
                             [WATCH_CALL], proposals=[WATCH]),
    }
    results = ev.run_cases(cases, ev.function_sessions(lambda case_id, turn, message: script[case_id]))
    assert [r["scores"]["passed"] for r in results] == [True, False, False, True]

    run_dir, ledger = tmp_path / "run", tmp_path / "failure_ledger.jsonl"
    versions = ev.collect_versions({"provider": "stub", "model": "scripted"}, "evaluation",
                                   ev.SET_FILES["evaluation"], fake=True)
    metrics = ev.write_reports(run_dir, results, versions, ledger)
    assert (metrics["cases_passed"], metrics["behavior_turns"]["total"]) == (2, 4)
    assert len((run_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()) == 4
    summary = (run_dir / "summary.md").read_text(encoding="utf-8")
    assert "FAKE AGENT RUN" in summary and "| Behavior accuracy |" in summary and "**T1-EVAL-016**" in summary
    run_info = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert set(run_info["versions"]["data_sha256"]) == set(ev.DATA_FILES) and run_info["versions"]["prompt_versions"] == ["test"]

    entries = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    assert [e["case_id"] for e in entries] == ["T1-EVAL-008", "T1-EVAL-016"]
    assert {"input", "data_version", "code_commit", "model", "prompt_version", "expected_result", "actual_result",
            "failure_type", "root_cause", "user_business_impact", "fix_mitigation", "regression_test",
            "retest_result", "residual_risk"} <= set(entries[1])
    assert entries[1]["failure_type"] == ["behavior", "facts"] and entries[1]["root_cause"] is None

    # A reviewer reads T1-EVAL-008, labels the turn DECLINE and re-scores; the ledger is not touched again.
    rows = [json.loads(line) for line in (run_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    rows[1]["turns"][0]["human_override"] = "DECLINE"
    rows[1]["human_review"]["faithful"] = True
    (run_dir / "results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    assert ev.main(["--rescore", str(run_dir)]) == 0
    rescored = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))["metrics"]
    assert rescored["cases_passed"] == 3 and rescored["faithfulness_reviewed"]["total"] == 1
    assert len(ledger.read_text(encoding="utf-8").splitlines()) == 2


def test_a_failed_turn_is_recorded_and_a_model_outage_stops_the_run(sets):
    case = case_by_id(sets, "T1-EVAL-019")

    def flaky(case_id, turn, message):
        if turn == 2:
            raise RuntimeError("boom")
        return reply("8 overdue: ORD-107 ... ORD-055.", [("get_overdue_orders", {}, "ok")], [("orders.csv", 81)])

    result = ev.run_case(case, ev.function_sessions(flaky))
    assert len(result["turns"]) == 3 and result["turns"][1]["error"] == "RuntimeError: boom"
    assert not result["scores"]["passed"]

    class ModelUnavailableError(RuntimeError):  # same name as service.ModelUnavailableError
        pass

    def outage(case_id, turn, message):
        raise ModelUnavailableError("The model API rejected the API key.")

    with pytest.raises(ev.RunAborted):
        ev.run_case(case, ev.function_sessions(outage))
