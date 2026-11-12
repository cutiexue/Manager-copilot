"""Regression tests for the faults in Evaluation Report V1 (2026-10-28), one per question it failed or left open.
Expected values are the report's own, recomputed from the course CSVs."""

import os

import pytest

import evidence_refs
from actions import ActionStore
from discovery import discover_issues
from period_output import compare_stage_periods, summarize_stage_output
from production_optimizer import optimize_fastest_plan
from service import today_note
from storage import SQLiteStore


def test_q05_q06_march_assembly_total_and_workday_average():
    [march] = summarize_stage_output("2026-03-01", "2026-03-31", "ASSEMBLY")["stages"]
    assert march["total_pieces"] == 18326
    assert (march["calendar_days"], march["scheduled_workdays"], march["recorded_workdays"]) == (31, 26, 26)
    assert march["mean_per_scheduled_workday"] == pytest.approx(704.85)
    assert len(march["source_rows"]) == 31 and march["missing_workdays"] == []


def test_missing_workdays_are_listed_not_counted_as_zero():
    result = summarize_stage_output("2026-03-30", "2026-04-02", "KNITTING")
    [period] = result["stages"]
    assert period["missing_workdays"] == ["2026-04-01", "2026-04-02"]
    assert "mean_per_scheduled_workday" not in period and period["recorded_workdays"] == 2


def test_q13_two_most_recent_complete_calendar_weeks():
    result = compare_stage_periods()
    assert result["first_period"] == {"date_from": "2026-03-16", "date_to": "2026-03-22"}
    assert result["second_period"] == {"date_from": "2026-03-23", "date_to": "2026-03-29"}
    assembly = next(s for s in result["stages"] if s["stage"] == "ASSEMBLY")
    assert (assembly["first_total"], assembly["second_total"], assembly["change"]) == (4781, 3214, -1567)
    assert assembly["change_percent"] == pytest.approx(-32.78)
    assert result["largest_decline"] == "ASSEMBLY" and result["complete_records"]


def test_period_inputs_are_checked():
    assert compare_stage_periods(first_from="2026-03-01")["status"] == "error"
    assert summarize_stage_output("2026-03-31", "2026-03-01")["status"] == "error"


def test_q11_top_five_orders_come_from_one_ranking_with_their_rows():
    result = discover_issues(max_findings=5, finding_type="order_at_risk")
    ids = [f["details"]["order_id"] for f in result["findings"]]
    assert ids == ["ORD-107", "ORD-120", "ORD-114", "ORD-083", "ORD-002"]
    assert all(f["type"] == "order_at_risk" for f in result["findings"])
    assert discover_issues(finding_type="nonsense")["status"] == "error"


def test_equal_severity_orders_rank_by_due_date():
    # ORD-029 (due today) and ORD-103 (due in 3 days) both score 0; the one due first ranks first.
    ids = [f["details"]["order_id"] for f in discover_issues(max_findings=10, finding_type="order_at_risk")["findings"]]
    assert ids[-1] == "ORD-029" and "ORD-103" not in ids


def test_q26_a_plan_says_which_producers_it_actually_uses():
    plan = optimize_fastest_plan("TOPS", 800)
    assert plan["include_in_house"] is True  # in-house was allowed ...
    assert plan["uses_in_house"] is False and "IN_HOUSE" not in plan["producers_used"]  # ... but not used
    assert sorted(plan["producers_used"]) == ["W2", "W6", "W8"]


def test_q18_evidence_follows_an_updated_csv(tmp_path, monkeypatch):
    path = tmp_path / "orders.csv"
    path.write_text("order_id,status\nORD-001,IN_PROGRESS\n", encoding="utf-8")
    monkeypatch.setattr(evidence_refs, "source_path", lambda source: path)
    assert evidence_refs._table("x")[1] == ["ORD-001", "IN_PROGRESS"]
    path.write_text("order_id,status\nORD-001,COMPLETE\n", encoding="utf-8")
    os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 1_000_000))
    assert evidence_refs._table("x")[1] == ["ORD-001", "COMPLETE"]


def test_q32_the_model_sees_that_a_proposal_was_already_confirmed(tmp_path):
    store = SQLiteStore(tmp_path / "app.db")
    store.setup()
    actions = ActionStore(store)
    actions.setup()
    proposal = actions.propose("note", {"order_id": "ORD-001", "text": "Priority handling."}, "chat", "s1")
    assert "waiting for Confirm" in today_note(actions, "s1").content
    actions.confirm(proposal["id"])
    note = today_note(actions, "s1").content
    assert proposal["id"] in note and "confirmed and saved" in note
    assert "proposals" not in today_note(actions, "another-session").content
