"""Scheduled jobs driven by a fake clock: no waiting, no duplicates after a restart."""

from datetime import datetime, timedelta

import pytest

import scheduler as jobs
from actions import APP_TZ, ActionStore
from storage import SQLiteStore

MORNING = datetime(2026, 10, 26, 7, 0, tzinfo=APP_TZ)


@pytest.fixture
def actions(tmp_path):
    store = SQLiteStore(tmp_path / "app.db")
    store.setup()
    store_actions = ActionStore(store)
    store_actions.setup()
    return store_actions


def test_the_scheduled_briefing_runs_once_per_day(actions):
    first = jobs.run_morning_briefing(actions, MORNING)
    again = jobs.run_morning_briefing(actions, MORNING + timedelta(hours=2))  # e.g. after a restart
    tomorrow = jobs.run_morning_briefing(actions, MORNING + timedelta(days=1))
    assert (first["created"], again["created"], tomorrow["created"]) == (True, False, True)
    assert [r["run_key"] for r in actions.list_briefing_runs()] == ["briefing:2026-10-27", "briefing:2026-10-26"]
    assert [a["title"] for a in actions.list_alerts()] == ["Morning briefing ready"] * 2
    manual = jobs.run_morning_briefing(actions, MORNING, trigger="manual")
    assert manual["created"] and len(actions.list_alerts()) == 2  # a manual run raises no alert


def test_a_failing_job_is_audited_and_the_scheduler_keeps_going(actions, monkeypatch):
    app_scheduler = jobs.AppScheduler(actions, clock=lambda: MORNING)

    def broken(store, now):
        raise RuntimeError("disk full")

    monkeypatch.setitem(jobs.JOBS, "reminders", broken)
    assert app_scheduler.run("reminders") is None
    assert app_scheduler.last["reminders"]["ok"] is False
    assert actions.list_audit()[0]["event"] == "job_failed"
    assert app_scheduler.run("proposal_expiry") == {"expired": 0}


def test_start_catches_up_and_reports_its_jobs(actions):
    app_scheduler = jobs.AppScheduler(actions, briefing_time="07:00", clock=lambda: MORNING + timedelta(hours=1))
    app_scheduler.start()
    try:
        status = app_scheduler.status()
        assert status["running"] and status["timezone"] == "Asia/Singapore"
        assert {job["id"] for job in status["jobs"]} == {"morning_briefing", "reminders", "watch_check", "proposal_expiry"}
        assert len(actions.list_briefing_runs()) == 1  # 08:00 start after a missed 07:00 run
    finally:
        app_scheduler.shutdown()
    with pytest.raises(ValueError):
        jobs.AppScheduler(actions, briefing_time="7am")
