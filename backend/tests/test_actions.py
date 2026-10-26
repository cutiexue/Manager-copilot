"""Follow-up actions: proposal -> confirm/cancel -> executed once, with expiry and a full audit trail."""

from datetime import datetime, timedelta

import pytest

from actions import APP_TZ, ActionNotFoundError, ActionStateError, ActionStore, parse_when
from storage import SQLiteStore

NOW = datetime(2026, 10, 24, 13, 30, tzinfo=APP_TZ)  # a Saturday


@pytest.fixture
def actions(tmp_path):
    store = SQLiteStore(tmp_path / "app.db")
    store.setup()
    store_actions = ActionStore(store)
    store_actions.setup()
    return store_actions


def events(actions):
    return [e["event"] for e in reversed(actions.list_audit())]


def test_nothing_is_saved_until_confirmed_and_a_second_confirm_changes_nothing(actions):
    proposal = actions.propose("reminder", {"text": "Chase Cotton Club", "when": "tomorrow 09:00",
                                            "order_id": "ord-2"}, "chat", "s1", now=NOW)
    assert proposal["status"] == "PROPOSED"
    assert proposal["payload"]["order_id"] == "ORD-002"
    assert actions.list_reminders() == []

    first = actions.confirm(proposal["id"], now=NOW)
    second = actions.confirm(proposal["id"], now=NOW)
    assert (first["already_done"], second["already_done"]) == (False, True)
    assert first["result"]["id"] == second["result"]["id"]
    assert len(actions.list_reminders()) == 1
    assert events(actions) == ["proposal_created", "confirmed", "executed"]


def test_cancelled_executed_and_expired_proposals_keep_their_state(actions):
    note = actions.propose("note", {"order_id": "ORD-107", "text": "Partial shipment agreed"}, "ui", now=NOW)
    assert actions.cancel(note["id"], now=NOW)["status"] == "CANCELLED"
    assert actions.cancel(note["id"], now=NOW)["status"] == "CANCELLED"  # idempotent
    with pytest.raises(ActionStateError, match="cancelled"):
        actions.confirm(note["id"], now=NOW)
    assert actions.list_notes() == []

    draft = actions.propose("chase_message", {"order_id": "ORD-120", "text": "Hello TrendCart"}, "chat", now=NOW)
    actions.confirm(draft["id"], now=NOW)
    with pytest.raises(ActionStateError, match="executed"):
        actions.cancel(draft["id"], now=NOW)

    stale = actions.propose("note", {"order_id": "ORD-002", "text": "Call washing"}, "chat", now=NOW)
    with pytest.raises(ActionStateError, match="expired"):
        actions.confirm(stale["id"], now=NOW + timedelta(hours=25))
    assert actions.get(stale["id"])["status"] == "EXPIRED"
    assert actions.list_notes() == []
    with pytest.raises(ActionNotFoundError):
        actions.confirm("no-such-id", now=NOW)


def test_expiry_job_closes_old_proposals(actions):
    actions.propose("note", {"order_id": "ORD-002", "text": "x"}, "chat", now=NOW)
    assert actions.expire_stale(now=NOW + timedelta(hours=1)) == 0
    assert actions.expire_stale(now=NOW + timedelta(hours=25)) == 1
    assert actions.list_proposals(status="EXPIRED")[0]["kind"] == "note"


def test_invalid_payloads_are_rejected_before_anything_is_stored(actions):
    with pytest.raises(ValueError, match="Unknown order"):
        actions.propose("note", {"order_id": "ORD-999", "text": "x"}, "chat", now=NOW)
    with pytest.raises(ValueError, match="order_id is required"):
        actions.propose("chase_message", {"text": "x"}, "chat", now=NOW)
    with pytest.raises(ValueError, match="non-empty"):
        actions.propose("reminder", {"text": "  "}, "chat", now=NOW)
    with pytest.raises(ValueError, match="kind"):
        actions.propose("delete_orders", {}, "chat", now=NOW)
    assert actions.list_proposals() == []


def test_a_due_reminder_alerts_once(actions):
    reminder = actions.propose("reminder", {"text": "Check ORD-107", "when": "in 2 hours"}, "ui", now=NOW)
    actions.confirm(reminder["id"], now=NOW)
    assert actions.fire_due_reminders(now=NOW + timedelta(hours=1)) == []
    fired = actions.fire_due_reminders(now=NOW + timedelta(hours=2))
    assert len(fired) == 1
    assert actions.fire_due_reminders(now=NOW + timedelta(hours=3)) == []
    alerts = actions.list_alerts(unread_only=True)
    assert [a["kind"] for a in alerts] == ["reminder"]
    actions.mark_alert_read(alerts[0]["id"], now=NOW)
    assert actions.counts() == {"pending_proposals": 0, "due_reminders": 1, "active_watches": 0, "unread_alerts": 0}
    assert actions.dismiss_reminder(fired[0], now=NOW)["status"] == "DISMISSED"


@pytest.mark.parametrize("text, expected", [
    ("tomorrow 09:00", "2026-10-25T09:00:00+08:00"),
    ("friday 3pm", "2026-10-30T15:00:00+08:00"),
    ("today 18:30", "2026-10-24T18:30:00+08:00"),
    ("in 2 hours", "2026-10-24T15:30:00+08:00"),
    ("2026-10-26", "2026-10-26T09:00:00+08:00"),
    ("2026-10-26T14:15", "2026-10-26T14:15:00+08:00"),
    (None, "2026-10-25T09:00:00+08:00"),
])
def test_reminder_times_use_the_singapore_calendar(text, expected):
    assert parse_when(text, NOW).isoformat() == expected


def test_past_and_unreadable_times_are_explained():
    with pytest.raises(ValueError, match="real calendar"):
        parse_when("2026-04-02", NOW)  # a dataset-era date is in the past for a real reminder
    with pytest.raises(ValueError, match="tomorrow 09:00"):
        parse_when("sometime soon", NOW)
