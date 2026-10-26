"""Morning briefing and discovery, plus the backend/frontend snapshot contract."""

import json
from pathlib import Path

from briefing import get_morning_briefing
from discovery import discover_issues

FIXTURE = Path(__file__).resolve().parents[2] / "frontend" / "src" / "fixtures" / "briefing.json"


def test_discovery_flags_the_assembly_drop():
    drops = [f for f in discover_issues(max_findings=50)["findings"]
             if f["type"] == "stage_output_drop"]
    assert [(f["details"]["stage"], f["details"]["change_percent"]) for f in drops] == [
        ("ASSEMBLY", -29.3)]
    assert drops[0]["details"]["recent_mean"] == 432.0
    assert drops[0]["details"]["baseline_mean"] == 611.0


def test_briefing_summary_figures():
    briefing = get_morning_briefing()
    assert briefing["status"] == "ok"
    assert briefing["yesterday"]["date"] == "2026-03-31"
    assert briefing["at_risk"]["count"] == 12
    assert briefing["total_findings"] == 14
    assert len(briefing["findings"]) == 5
    assert briefing["coverage_complete"] is True


def test_frontend_fixture_matches_backend_output():
    # 前端目前读取的是晨报快照；后端规则一改，这里会提醒重新生成 fixture。
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert fixture["briefing"] == json.loads(json.dumps(get_morning_briefing(narrative_rows=True)))


def test_summary_comes_first_and_every_sentence_has_sources():
    summary = get_morning_briefing()["summary"]
    assert summary["text"] == (
        "12 unfinished orders need attention: 8 are overdue, 3 are due within 3 days and 1 has had no "
        "recorded activity for 7 days or more. The most overdue is ORD-107 for Northwind Apparel, 16 days "
        "past its due date. ASSEMBLY output fell 29.3% over the last 3 workdays compared with the 7 before. "
        "Both unfinished Maple & Co orders are overdue or quiet. Yesterday (2026-03-31) ASSEMBLY completed "
        "455 pieces, 11.8% below its 7-workday average; the other stages were within 3.6% of theirs.")
    points = summary["points"]
    assert [p["kind"] for p in points] == [
        "orders_at_risk", "most_overdue", "stage_output_drop", "customer_slipping", "yesterday"]
    assert [len(p["evidence"]["source_rows"]) for p in points] == [12, 1, 10, 2, 32]
    assert points[1]["evidence"]["source_rows"] == [
        {"source": "track1/data/orders.csv", "row": 81, "key": "ORD-107"}]


def test_checks_give_every_finding_a_level_and_state_the_rule():
    briefing = get_morning_briefing()
    checks = briefing["checks"]
    assert [(c["type"], c["total"], [(lv["level"], lv["count"]) for lv in c["levels"]]) for c in checks] == [
        ("order_at_risk", 12, [("act", 6), ("watch", 6)]),
        ("stage_output_drop", 1, [("act", 1)]),
        ("customer_slipping", 1, [("act", 1)])]
    assert (briefing["act_count"], briefing["watch_count"]) == (8, 6)
    # Every at-risk order is marked: act now when 7+ days late or 7+ days idle, otherwise watch.
    assert [(lv["label"], lv["rule"]) for lv in checks[0]["levels"]] == [
        ("Act now", "Late or idle 7+ days"), ("Watch", "Late under 7 days or due within 3 days")]
    # Act now first, highest score first; orders not yet late follow by due date.
    assert [(i["name"], i["tag"], i["level"]) for i in checks[0]["items"]] == [
        ("ORD-107", "16 days late", "act"), ("ORD-120", "15 days late", "act"), ("ORD-114", "9 days late", "act"),
        ("ORD-083", "9 days late", "act"), ("ORD-002", "3 days late · 9 days idle", "act"),
        ("ORD-005", "8 days idle", "act"), ("ORD-093", "3 days late", "watch"), ("ORD-020", "1 day late", "watch"),
        ("ORD-055", "1 day late", "watch"), ("ORD-029", "due today", "watch"), ("ORD-108", "due in 2 days", "watch"),
        ("ORD-103", "due in 3 days", "watch")]
    stage, customer = checks[1]["items"][0], checks[2]["items"][0]
    assert (stage["context"], stage["tag"]) == ("432 vs 611 pcs/workday", "−29.3%")
    assert checks[1]["levels"][0]["rule"] == "Output down 20%+ (last 3 workdays vs previous 7)"
    assert (customer["context"], customer["tag"]) == ("ORD-083, ORD-093", "2 orders")
    assert checks[2]["levels"][0]["rule"] == "2+ unfinished orders, all late or idle"


def test_monday_briefing_reports_the_last_workday():
    # Sunday is a rest day, so a Monday briefing reports Saturday instead of an empty section.
    briefing = get_morning_briefing("2026-03-30")
    section = briefing["yesterday"]
    assert (section["date"], section["label"], section["is_workday"], len(section["stages"])) == (
        "2026-03-28", "Last workday", True, 4)
    assert briefing["summary"]["points"][-1]["text"].startswith(
        "Last workday (2026-03-28) ASSEMBLY completed 445 pieces")
    # On any other day it is literally yesterday.
    assert get_morning_briefing()["yesterday"]["label"] == "Yesterday"
    assert get_morning_briefing("2026-03-29")["yesterday"]["date"] == "2026-03-28"


def test_snapshot_date_in_another_spelling_is_not_a_scenario():
    assert not any("scenario" in w for w in get_morning_briefing("20260401")["warnings"])
    assert any("scenario" in w for w in get_morning_briefing("2026-03-30")["warnings"])


def test_narrative_tells_yesterday_risk_and_today_in_three_sentences():
    """The track asks for a briefing that is structured *and* prose: yesterday, at risk, today."""
    briefing = get_morning_briefing(narrative_rows=True)
    narrative = briefing["narrative"]
    assert [s["topic"] for s in narrative["sentences"]] == ["yesterday", "at_risk", "today"]
    assert narrative["text"] == (
        "Yesterday assembly made 455 pieces, 11.8% below its 7-workday average; knitting was next "
        "lowest, 3.6% below. 12 orders are at risk (8 overdue, 3 due within 3 days, 1 idle 7+ days); "
        "ORD-107 for Northwind Apparel is the furthest behind at 16 days late. 8 items need action "
        "today: 6 orders late or idle 7+ days, the 29.3% drop in assembly output over the last 3 "
        "workdays and customer Maple & Co (both open orders slipping).")
    # The prose adds no numbers of its own: each one is in the structured briefing.
    assert briefing["at_risk"]["count"] == 12 and briefing["act_count"] == 8
    act = [i for c in briefing["checks"] for i in c["items"] if i["level"] == "act"]
    today_rows = {(r["source"], r["row"]) for r in narrative["sentences"][2]["evidence"]["source_rows"]}
    assert today_rows == {(r["source"], r["row"]) for i in act for r in i["finding"]["evidence"]["source_rows"]}
    assert narrative["sentences"][1]["evidence"]["source_rows"] == briefing["at_risk"]["source_rows"]


def test_narrative_on_a_monday_and_on_a_quiet_day():
    monday = get_morning_briefing("2026-03-30")["narrative"]["sentences"][0]["text"]
    assert monday.startswith("On Sat 28 Mar, the last workday, assembly made 445 pieces")
    quiet = get_morning_briefing("2026-02-02", narrative_rows=True)["narrative"]["sentences"]
    assert quiet[1]["text"] == "No order is overdue, due within 3 days or idle 7+ days."
    assert quiet[2]["text"] == "Nothing needs action today."
    assert quiet[1]["evidence"] is None and quiet[2]["evidence"] is None


def test_agent_gets_the_narrative_without_repeating_its_rows():
    tool = get_morning_briefing()["narrative"]
    page = get_morning_briefing(narrative_rows=True)["narrative"]
    assert tool["text"] == page["text"]
    assert all(set(s) == {"topic", "text"} for s in tool["sentences"])
