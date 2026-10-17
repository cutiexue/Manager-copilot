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
    assert fixture["briefing"] == json.loads(json.dumps(get_morning_briefing()))
