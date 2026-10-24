"""Agent tools for follow-ups. They only create proposals: nothing is saved until the manager
presses Confirm in the app, and there is deliberately no tool that confirms."""

from contextlib import contextmanager
from contextvars import ContextVar

import watches

_context = ContextVar("action_context", default=None)
_UNAVAILABLE = {"status": "unavailable",
                "message": "Follow-up actions are only available in an app conversation."}
_NOT_SAVED = ("Not saved yet: the manager must press Confirm on the card in the app. Say so, "
              "and never claim it is done.")


@contextmanager
def action_context(actions, session_id):
    """Make the action store and conversation available to the tools for one chat turn."""
    token = _context.set({"actions": actions, "session_id": session_id})
    try:
        yield
    finally:
        _context.reset(token)


def _propose(kind, payload):
    context = _context.get()
    if context is None:
        return dict(_UNAVAILABLE)
    try:
        proposal = context["actions"].propose(kind, payload, "chat", context["session_id"])
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}
    return {"status": "proposed",
            "proposal": {key: proposal[key] for key in ("id", "kind", "status", "summary", "payload", "expires_at")},
            "message": _NOT_SAVED}


def propose_reminder(text, when="tomorrow 09:00", order_id=None, subject=None):
    """Propose an in-app reminder for the manager."""
    return _propose("reminder", {"text": text, "when": when, "order_id": order_id, "subject": subject})


def propose_order_note(order_id, text):
    """Propose a local note on an order (never written to the course CSV)."""
    return _propose("note", {"order_id": order_id, "text": text})


def draft_chase_message(order_id, text):
    """Propose a chase-up message draft for the order's customer; it is never sent automatically."""
    return _propose("chase_message", {"order_id": order_id, "text": text})


def propose_watch(order_id, condition, deadline=None, stage=None):
    """Propose a standing watch on an order, checked against the data snapshots."""
    return _propose("watch", {"order_id": order_id, "condition": condition, "deadline": deadline, "stage": stage})


def list_follow_ups(kind=None):
    """List pending proposals, reminders, notes, chase-up drafts, watches and unread alerts."""
    context = _context.get()
    if context is None:
        return dict(_UNAVAILABLE)
    try:
        items = context["actions"].follow_ups(kind)
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}
    version = context["actions"].data_version()
    return {"status": "ok", **items, "watch_data_snapshot": watches.version_info(version),
            "note": "Watches are checked against scripted data snapshots, not live factory data."}
