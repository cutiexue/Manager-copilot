"""Follow-up actions: proposals, what they create once confirmed, alerts, and the audit trail.

The agent can only create proposals. A proposal turns into a reminder, order note, chase-up draft
or watch only through confirm(), which the app calls when the manager presses Confirm. Confirming
twice returns the first result instead of creating a second one; a cancelled or expired proposal
cannot be confirmed. Every change is written to audit_events, which has no update or delete path.

Times use the application clock (Asia/Singapore). Watches use the data clock instead: the
scripted snapshot in use (see watches.py), never the computer's date.
"""

import json
import re
from datetime import date, datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import watches
from data_loader import load_orders
from tools import canonical_order_id

APP_TZ = ZoneInfo("Asia/Singapore")
PROPOSAL_TTL = timedelta(hours=24)
KINDS = ("reminder", "note", "chase_message", "watch")
_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

SCHEMA = [
    '''CREATE TABLE IF NOT EXISTS action_proposals (
        id TEXT PRIMARY KEY, kind TEXT NOT NULL, status TEXT NOT NULL, source TEXT NOT NULL,
        session_id TEXT, payload TEXT NOT NULL, summary TEXT NOT NULL, reason TEXT,
        created_at TEXT NOT NULL, expires_at TEXT NOT NULL, decided_at TEXT,
        result_kind TEXT, result_id TEXT, error TEXT)''',
    '''CREATE TABLE IF NOT EXISTS reminders (
        id TEXT PRIMARY KEY, proposal_id TEXT NOT NULL UNIQUE, order_id TEXT, subject TEXT,
        text TEXT NOT NULL, remind_at TEXT NOT NULL, status TEXT NOT NULL,
        created_at TEXT NOT NULL, due_at TEXT, dismissed_at TEXT)''',
    '''CREATE TABLE IF NOT EXISTS order_notes (
        id TEXT PRIMARY KEY, proposal_id TEXT NOT NULL UNIQUE, order_id TEXT NOT NULL,
        text TEXT NOT NULL, created_at TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS chase_drafts (
        id TEXT PRIMARY KEY, proposal_id TEXT NOT NULL UNIQUE, order_id TEXT NOT NULL,
        customer TEXT NOT NULL, text TEXT NOT NULL, created_at TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS watches (
        id TEXT PRIMARY KEY, proposal_id TEXT NOT NULL UNIQUE, order_id TEXT NOT NULL,
        condition TEXT NOT NULL, deadline TEXT, stage TEXT, baseline TEXT NOT NULL,
        status TEXT NOT NULL, summary TEXT NOT NULL, created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL, last_checked_at TEXT, last_result TEXT, outcome TEXT)''',
    '''CREATE TABLE IF NOT EXISTS watch_checks (
        id INTEGER PRIMARY KEY AUTOINCREMENT, watch_id TEXT NOT NULL, checked_at TEXT NOT NULL,
        data_version TEXT NOT NULL, data_date TEXT NOT NULL, result TEXT NOT NULL, detail TEXT)''',
    '''CREATE TABLE IF NOT EXISTS alerts (
        id TEXT PRIMARY KEY, kind TEXT NOT NULL, ref_id TEXT, title TEXT NOT NULL, body TEXT,
        dedupe_key TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL, read_at TEXT)''',
    '''CREATE TABLE IF NOT EXISTS audit_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, actor TEXT NOT NULL,
        event TEXT NOT NULL, proposal_id TEXT, target_kind TEXT, target_id TEXT, detail TEXT)''',
    '''CREATE TABLE IF NOT EXISTS briefing_runs (
        id TEXT PRIMARY KEY, run_key TEXT NOT NULL UNIQUE, as_of_date TEXT NOT NULL,
        trigger TEXT NOT NULL, generated_at TEXT NOT NULL, payload TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS app_state (key TEXT PRIMARY KEY, value TEXT NOT NULL)''',
]


class ActionNotFoundError(LookupError):
    """No proposal, reminder, watch or alert has this ID."""


class ActionStateError(Exception):
    """The request does not fit the item's state (e.g. confirming a cancelled proposal)."""


def now_sg():
    return datetime.now(APP_TZ).replace(microsecond=0)


def _iso(moment):
    return moment.astimezone(APP_TZ).isoformat(timespec="seconds")


def parse_when(value, now):
    """Turn 'tomorrow 09:00', 'friday 3pm', 'in 2 hours' or an ISO date/time into an aware datetime."""
    text = (value or "tomorrow 09:00").strip()
    lowered = re.sub(r"\s+", " ", text.lower())
    moment = None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        moment = datetime.combine(date.fromisoformat(text), time(9, 0), APP_TZ)
    else:
        try:
            moment = datetime.fromisoformat(text)
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=APP_TZ)
        except ValueError:
            pass
    if moment is None:
        relative = re.fullmatch(r"in (\d{1,3}) ?(minutes?|mins?|hours?|hrs?|days?)", lowered)
        if relative:
            amount, unit = int(relative.group(1)), relative.group(2)
            step = timedelta(minutes=1) if unit.startswith("min") else timedelta(hours=1) if unit.startswith("h") else timedelta(days=1)
            moment = now + amount * step
    if moment is None:
        named = re.fullmatch(r"(today|tomorrow|%s)(?: (?:at )?(\d{1,2})(?::(\d{2}))? ?(am|pm)?)?" % "|".join(_WEEKDAYS), lowered)
        if named:
            word, hour, minute, half = named.groups()
            if word == "today":
                day = now.date()
            elif word == "tomorrow":
                day = now.date() + timedelta(days=1)
            else:
                ahead = (_WEEKDAYS.index(word) - now.weekday()) % 7 or 7
                day = now.date() + timedelta(days=ahead)
            hour = int(hour) if hour is not None else 9
            if half == "pm" and hour < 12:
                hour += 12
            if half == "am" and hour == 12:
                hour = 0
            if not 0 <= hour <= 23 or (minute is not None and not 0 <= int(minute) <= 59):
                raise ValueError("Use a time of day between 00:00 and 23:59.")
            moment = datetime.combine(day, time(hour, int(minute or 0)), APP_TZ)
    if moment is None:
        raise ValueError("Use a time like 'tomorrow 09:00', 'friday 3pm', 'in 2 hours' or '2026-10-25T09:00'.")
    moment = moment.astimezone(APP_TZ).replace(second=0, microsecond=0)
    if moment < now - timedelta(minutes=1):
        raise ValueError(f"That time has already passed: reminders use the real calendar (now {_iso(now)}, "
                         "Singapore time), not the dataset date.")
    if moment > now + timedelta(days=366):
        raise ValueError("Reminders can be set at most a year ahead.")
    return moment


def _text(value, name, limit):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text.")
    if len(value) > limit:
        raise ValueError(f"{name} must be at most {limit} characters.")
    return value.strip()


def _order(value, required=True):
    if value in (None, ""):
        if required:
            raise ValueError("order_id is required.")
        return None
    order_id = canonical_order_id(value) if isinstance(value, str) else None
    order = next((o for o in load_orders() if o["order_id"] == order_id), None) if order_id else None
    if order is None:
        raise ValueError(f"Unknown order {value!r}. Use an ID like ORD-107.")
    return order


class ActionStore:
    """All follow-up state, in the same SQLite file as the conversations."""

    def __init__(self, store):
        self.store = store

    def setup(self):
        with self.store.connection() as conn:
            for statement in SCHEMA:
                conn.execute(statement)

    # ---- audit -------------------------------------------------------------------------------
    @staticmethod
    def _audit(conn, actor, event, at, proposal_id=None, target_kind=None, target_id=None, detail=None):
        conn.execute('INSERT INTO audit_events (at, actor, event, proposal_id, target_kind, target_id, detail) '
                     'VALUES (?,?,?,?,?,?,?)',
                     (_iso(at), actor, event, proposal_id, target_kind, target_id,
                      json.dumps(detail, ensure_ascii=False) if detail is not None else None))

    def record(self, actor, event, detail=None, now=None):
        """Write one audit event that is not tied to a proposal (e.g. a scheduler failure)."""
        with self.store.connection() as conn:
            self._audit(conn, actor, event, now or now_sg(), detail=detail)

    def list_audit(self, limit=100):
        with self.store.connection() as conn:
            rows = conn.execute('SELECT * FROM audit_events ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
        return [{**dict(row), "detail": json.loads(row["detail"]) if row["detail"] else None} for row in rows]

    # ---- data snapshot used by watches -----------------------------------------------------------
    def data_version(self):
        with self.store.connection() as conn:
            row = conn.execute("SELECT value FROM app_state WHERE key='data_version'").fetchone()
        return row["value"] if row else watches.BASE_VERSION

    def set_data_version(self, version_id, actor="user", now=None):
        info = watches.version_info(version_id)
        now = now or now_sg()
        with self.store.connection() as conn:
            conn.execute("INSERT INTO app_state (key, value) VALUES ('data_version', ?) "
                         "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (version_id,))
            self._audit(conn, actor, "data_snapshot_loaded", now, detail=info)
        return info

    # ---- proposals -------------------------------------------------------------------------------
    def _prepare(self, kind, payload, now):
        """Validate a proposal's payload and return (clean payload, summary)."""
        if kind not in KINDS:
            raise ValueError(f"kind must be one of {', '.join(KINDS)}.")
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object.")
        if kind == "reminder":
            order = _order(payload.get("order_id"), required=False)
            subject = payload.get("subject")
            subject = _text(subject, "subject", 200) if subject not in (None, "") else None
            text = _text(payload.get("text"), "text", 500)
            remind_at = parse_when(payload.get("remind_at") or payload.get("when"), now)
            about = order["order_id"] if order else subject or "general"
            clean = {"text": text, "remind_at": _iso(remind_at), "order_id": order and order["order_id"],
                     "subject": subject, "customer": order and order["customer"]}
            return clean, f"Reminder · {remind_at.strftime('%a %d %b %H:%M')} · {about}: {text}"
        if kind == "note":
            order = _order(payload.get("order_id"))
            text = _text(payload.get("text"), "text", 1000)
            return {"order_id": order["order_id"], "text": text}, f"Note on {order['order_id']}: {text}"
        if kind == "chase_message":
            order = _order(payload.get("order_id"))
            text = _text(payload.get("text"), "text", 2000)
            return ({"order_id": order["order_id"], "customer": order["customer"], "text": text},
                    f"Chase-up draft for {order['customer']} ({order['order_id']}); not sent")
        order = _order(payload.get("order_id"))
        version = self.data_version()
        state = watches.order_state(order["order_id"], version)
        data_date = date.fromisoformat(watches.version_info(version)["date"])
        deadline, stage = watches.check_definition(payload.get("condition"), state, data_date,
                                                   payload.get("deadline"), payload.get("stage"))
        condition = payload["condition"]
        summary = watches.describe(condition, order["order_id"], deadline, stage)
        return ({"order_id": order["order_id"], "condition": condition, "deadline": deadline, "stage": stage,
                 "current": watches.baseline(state), "data_version": version}, summary)

    def propose(self, kind, payload, source, session_id=None, reason=None, now=None):
        now = now or now_sg()
        if source not in ("chat", "ui"):
            raise ValueError("source must be chat or ui.")
        clean, summary = self._prepare(kind, payload, now)
        proposal_id = str(uuid4())
        with self.store.connection() as conn:
            conn.execute('INSERT INTO action_proposals (id, kind, status, source, session_id, payload, summary, '
                         'reason, created_at, expires_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
                         (proposal_id, kind, "PROPOSED", source, session_id, json.dumps(clean, ensure_ascii=False),
                          summary, reason, _iso(now), _iso(now + PROPOSAL_TTL)))
            self._audit(conn, "agent" if source == "chat" else "user", "proposal_created", now, proposal_id,
                        kind, None, {"summary": summary})
        return self.get(proposal_id)

    @staticmethod
    def _proposal(row):
        item = dict(row)
        item["payload"] = json.loads(item["payload"])
        return item

    def get(self, proposal_id):
        with self.store.connection() as conn:
            row = conn.execute('SELECT * FROM action_proposals WHERE id=?', (proposal_id,)).fetchone()
        if row is None:
            raise ActionNotFoundError("Proposal not found.")
        return self._proposal(row)

    def list_proposals(self, status=None, session_id=None, limit=100):
        query, args = 'SELECT * FROM action_proposals WHERE 1=1', []
        if status:
            query += ' AND status=?'
            args.append(status)
        if session_id:
            query += ' AND session_id=?'
            args.append(session_id)
        with self.store.connection() as conn:
            rows = conn.execute(query + ' ORDER BY created_at DESC, id LIMIT ?', (*args, limit)).fetchall()
        return [self._proposal(row) for row in rows]

    def confirm(self, proposal_id, now=None):
        """Execute a proposal exactly once. Returns {proposal, result, already_done}."""
        now = now or now_sg()
        with self.store.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')  # one writer at a time: a double click cannot execute twice
            row = conn.execute('SELECT * FROM action_proposals WHERE id=?', (proposal_id,)).fetchone()
            if row is None:
                raise ActionNotFoundError("Proposal not found.")
            proposal = self._proposal(row)
            if proposal["status"] == "EXECUTED":
                return {"proposal": proposal, "result": self._target(conn, proposal), "already_done": True}
            if proposal["status"] != "PROPOSED":
                raise ActionStateError(f"This proposal is {proposal['status'].lower()} and can no longer be confirmed.")
            if datetime.fromisoformat(proposal["expires_at"]) < now:
                conn.execute("UPDATE action_proposals SET status='EXPIRED', decided_at=? WHERE id=?", (_iso(now), proposal_id))
                self._audit(conn, "system", "proposal_expired", now, proposal_id, proposal["kind"])
                conn.commit()
                raise ActionStateError("This proposal expired after 24 hours; ask again to create a new one.")
            self._audit(conn, "user", "confirmed", now, proposal_id, proposal["kind"])
            try:
                result_kind, result_id = self._execute(conn, proposal, now)
            except ValueError as exc:
                conn.execute("UPDATE action_proposals SET status='FAILED', decided_at=?, error=? WHERE id=?",
                             (_iso(now), str(exc), proposal_id))
                self._audit(conn, "system", "failed", now, proposal_id, proposal["kind"], detail={"error": str(exc)})
                conn.commit()
                raise ActionStateError(f"Could not carry this out: {exc}") from None
            conn.execute("UPDATE action_proposals SET status='EXECUTED', decided_at=?, result_kind=?, result_id=? "
                         "WHERE id=?", (_iso(now), result_kind, result_id, proposal_id))
            self._audit(conn, "system", "executed", now, proposal_id, result_kind, result_id)
            proposal = self._proposal(conn.execute('SELECT * FROM action_proposals WHERE id=?', (proposal_id,)).fetchone())
            return {"proposal": proposal, "result": self._target(conn, proposal), "already_done": False}

    def cancel(self, proposal_id, now=None):
        now = now or now_sg()
        with self.store.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT * FROM action_proposals WHERE id=?', (proposal_id,)).fetchone()
            if row is None:
                raise ActionNotFoundError("Proposal not found.")
            proposal = self._proposal(row)
            if proposal["status"] == "CANCELLED":
                return proposal
            if proposal["status"] != "PROPOSED":
                raise ActionStateError(f"This proposal is {proposal['status'].lower()} and cannot be cancelled.")
            conn.execute("UPDATE action_proposals SET status='CANCELLED', decided_at=? WHERE id=?", (_iso(now), proposal_id))
            self._audit(conn, "user", "cancelled", now, proposal_id, proposal["kind"])
            return self._proposal(conn.execute('SELECT * FROM action_proposals WHERE id=?', (proposal_id,)).fetchone())

    def expire_stale(self, now=None):
        now = now or now_sg()
        with self.store.connection() as conn:
            rows = conn.execute("SELECT id, kind FROM action_proposals WHERE status='PROPOSED' AND expires_at < ?",
                                (_iso(now),)).fetchall()
            for row in rows:
                conn.execute("UPDATE action_proposals SET status='EXPIRED', decided_at=? WHERE id=? AND status='PROPOSED'",
                             (_iso(now), row["id"]))
                self._audit(conn, "system", "proposal_expired", now, row["id"], row["kind"])
        return len(rows)

    def _execute(self, conn, proposal, now):
        payload, new_id, at = proposal["payload"], str(uuid4()), _iso(now)
        kind = proposal["kind"]
        if kind == "reminder":
            conn.execute('INSERT INTO reminders (id, proposal_id, order_id, subject, text, remind_at, status, created_at) '
                         'VALUES (?,?,?,?,?,?,?,?)', (new_id, proposal["id"], payload["order_id"], payload["subject"],
                                                      payload["text"], payload["remind_at"], "SCHEDULED", at))
            return "reminder", new_id
        if kind == "note":
            _order(payload["order_id"])
            conn.execute('INSERT INTO order_notes (id, proposal_id, order_id, text, created_at) VALUES (?,?,?,?,?)',
                         (new_id, proposal["id"], payload["order_id"], payload["text"], at))
            return "note", new_id
        if kind == "chase_message":
            conn.execute('INSERT INTO chase_drafts (id, proposal_id, order_id, customer, text, created_at) '
                         'VALUES (?,?,?,?,?,?)', (new_id, proposal["id"], payload["order_id"], payload["customer"],
                                                  payload["text"], at))
            return "chase_draft", new_id
        # A watch starts from the order as the current snapshot shows it, checked again now.
        version = self._state(conn, "data_version") or watches.BASE_VERSION
        state = watches.order_state(payload["order_id"], version)
        data_date = date.fromisoformat(watches.version_info(version)["date"])
        deadline, stage = watches.check_definition(payload["condition"], state, data_date,
                                                   payload["deadline"], payload["stage"])
        summary = watches.describe(payload["condition"], payload["order_id"], deadline, stage)
        conn.execute('INSERT INTO watches (id, proposal_id, order_id, condition, deadline, stage, baseline, status, '
                     'summary, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                     (new_id, proposal["id"], payload["order_id"], payload["condition"], deadline, stage,
                      json.dumps(watches.baseline(state)), "ACTIVE", summary, at, at))
        return "watch", new_id

    @staticmethod
    def _state(conn, key):
        row = conn.execute('SELECT value FROM app_state WHERE key=?', (key,)).fetchone()
        return row["value"] if row else None

    def _target(self, conn, proposal):
        table = {"reminder": "reminders", "note": "order_notes", "chase_draft": "chase_drafts",
                 "watch": "watches"}.get(proposal["result_kind"])
        if not table:
            return None
        row = conn.execute(f'SELECT * FROM {table} WHERE id=?', (proposal["result_id"],)).fetchone()
        return self._watch(row) if table == "watches" and row else dict(row) if row else None

    # ---- what confirmed proposals created ---------------------------------------------------------
    def list_reminders(self, status=None):
        with self.store.connection() as conn:
            query = 'SELECT * FROM reminders' + (' WHERE status=?' if status else '') + ' ORDER BY remind_at, id'
            return [dict(row) for row in conn.execute(query, (status,) if status else ()).fetchall()]

    def fire_due_reminders(self, now=None):
        """Mark reminders whose time has come as due and raise one alert each."""
        now = now or now_sg()
        fired = []
        with self.store.connection() as conn:
            rows = conn.execute("SELECT * FROM reminders WHERE status='SCHEDULED' AND remind_at <= ?",
                                (_iso(now),)).fetchall()
            for row in rows:
                conn.execute("UPDATE reminders SET status='DUE', due_at=? WHERE id=? AND status='SCHEDULED'",
                             (_iso(now), row["id"]))
                about = row["order_id"] or row["subject"] or "Reminder"
                self._raise_alert(conn, "reminder", row["id"], f"Reminder · {about}", row["text"],
                                  f"reminder:{row['id']}", now)
                self._audit(conn, "scheduler", "reminder_due", now, row["proposal_id"], "reminder", row["id"])
                fired.append(row["id"])
        return fired

    def dismiss_reminder(self, reminder_id, now=None):
        now = now or now_sg()
        with self.store.connection() as conn:
            row = conn.execute('SELECT * FROM reminders WHERE id=?', (reminder_id,)).fetchone()
            if row is None:
                raise ActionNotFoundError("Reminder not found.")
            if row["status"] != "DISMISSED":
                conn.execute("UPDATE reminders SET status='DISMISSED', dismissed_at=? WHERE id=?", (_iso(now), reminder_id))
                self._audit(conn, "user", "reminder_dismissed", now, row["proposal_id"], "reminder", reminder_id)
            return dict(conn.execute('SELECT * FROM reminders WHERE id=?', (reminder_id,)).fetchone())

    def list_notes(self, order_id=None):
        with self.store.connection() as conn:
            if order_id:
                rows = conn.execute('SELECT * FROM order_notes WHERE order_id=? ORDER BY created_at DESC',
                                    (canonical_order_id(order_id) or order_id,)).fetchall()
            else:
                rows = conn.execute('SELECT * FROM order_notes ORDER BY created_at DESC').fetchall()
        return [dict(row) for row in rows]

    def list_drafts(self):
        with self.store.connection() as conn:
            return [dict(row) for row in conn.execute('SELECT * FROM chase_drafts ORDER BY created_at DESC').fetchall()]

    # ---- watches ---------------------------------------------------------------------------------
    @staticmethod
    def _watch(row):
        item = dict(row)
        item["baseline"] = json.loads(item["baseline"])
        return item

    def list_watches(self, status=None):
        with self.store.connection() as conn:
            query = 'SELECT * FROM watches' + (' WHERE status=?' if status else '') + ' ORDER BY created_at DESC, id'
            return [self._watch(row) for row in conn.execute(query, (status,) if status else ()).fetchall()]

    def get_watch(self, watch_id):
        with self.store.connection() as conn:
            row = conn.execute('SELECT * FROM watches WHERE id=?', (watch_id,)).fetchone()
        if row is None:
            raise ActionNotFoundError("Watch not found.")
        return self._watch(row)

    def set_watch_status(self, watch_id, action, now=None):
        """Pause, resume or cancel a watch; finished watches cannot change."""
        now = now or now_sg()
        moves = {"pause": ("ACTIVE", "PAUSED"), "resume": ("PAUSED", "ACTIVE"), "cancel": (None, "CANCELLED")}
        done = {"pause": "paused", "resume": "resumed", "cancel": "cancelled"}
        if action not in moves:
            raise ValueError("action must be pause, resume or cancel.")
        before, after = moves[action]
        with self.store.connection() as conn:
            row = conn.execute('SELECT * FROM watches WHERE id=?', (watch_id,)).fetchone()
            if row is None:
                raise ActionNotFoundError("Watch not found.")
            if row["status"] == after:
                return self._watch(row)
            if row["status"] in ("TRIGGERED", "RESOLVED", "CANCELLED") or (before and row["status"] != before):
                raise ActionStateError(f"This watch is {row['status'].lower()} and cannot be {done[action]}.")
            conn.execute('UPDATE watches SET status=?, updated_at=? WHERE id=?', (after, _iso(now), watch_id))
            self._audit(conn, "user", f"watch_{done[action]}", now, row["proposal_id"], "watch", watch_id)
            return self._watch(conn.execute('SELECT * FROM watches WHERE id=?', (watch_id,)).fetchone())

    def record_watch_check(self, watch, now, version_id, result, detail):
        """Store a check when its result or snapshot changed; fire or close the watch when due."""
        info = watches.version_info(version_id)
        with self.store.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            current = conn.execute('SELECT status FROM watches WHERE id=?', (watch["id"],)).fetchone()
            if current is None or current["status"] != "ACTIVE":
                return
            last = conn.execute('SELECT data_version, result FROM watch_checks WHERE watch_id=? ORDER BY id DESC LIMIT 1',
                                (watch["id"],)).fetchone()
            if last is None or (last["data_version"], last["result"]) != (version_id, result):
                conn.execute('INSERT INTO watch_checks (watch_id, checked_at, data_version, data_date, result, detail) '
                             'VALUES (?,?,?,?,?,?)', (watch["id"], _iso(now), version_id, info["date"], result, detail))
            status = {"met": "TRIGGERED", "resolved": "RESOLVED"}.get(result, "ACTIVE")
            conn.execute('UPDATE watches SET last_checked_at=?, last_result=?, status=?, updated_at=?, outcome=? WHERE id=?',
                         (_iso(now), result, status, _iso(now), detail if status != "ACTIVE" else None, watch["id"]))
            if result == "met":
                self._raise_alert(conn, "watch", watch["id"], f"Watch · {watch['order_id']}", detail,
                                  f"watch:{watch['id']}", now)
                self._audit(conn, "scheduler", "watch_triggered", now, watch["proposal_id"], "watch", watch["id"],
                            {"detail": detail, "data_version": version_id})
            elif result == "resolved":
                self._audit(conn, "scheduler", "watch_resolved", now, watch["proposal_id"], "watch", watch["id"],
                            {"detail": detail, "data_version": version_id})

    def watch_checks(self, watch_id):
        with self.store.connection() as conn:
            return [dict(row) for row in conn.execute('SELECT * FROM watch_checks WHERE watch_id=? ORDER BY id',
                                                      (watch_id,)).fetchall()]

    # ---- alerts ----------------------------------------------------------------------------------
    def _raise_alert(self, conn, kind, ref_id, title, body, dedupe_key, now):
        """Insert an alert unless one with the same key exists, so a repeat check never repeats it."""
        created = conn.execute('INSERT OR IGNORE INTO alerts (id, kind, ref_id, title, body, dedupe_key, created_at) '
                               'VALUES (?,?,?,?,?,?,?)',
                               (str(uuid4()), kind, ref_id, title, body, dedupe_key, _iso(now))).rowcount
        if created:
            self._audit(conn, "system", "alert_raised", now, None, kind, ref_id, {"title": title})
        return bool(created)

    def raise_alert(self, kind, ref_id, title, body, dedupe_key, now=None):
        with self.store.connection() as conn:
            return self._raise_alert(conn, kind, ref_id, title, body, dedupe_key, now or now_sg())

    def list_alerts(self, unread_only=False, limit=100):
        with self.store.connection() as conn:
            query = 'SELECT * FROM alerts' + (' WHERE read_at IS NULL' if unread_only else '')
            return [dict(row) for row in conn.execute(query + ' ORDER BY created_at DESC, id LIMIT ?', (limit,)).fetchall()]

    def mark_alert_read(self, alert_id, now=None):
        now = now or now_sg()
        with self.store.connection() as conn:
            row = conn.execute('SELECT * FROM alerts WHERE id=?', (alert_id,)).fetchone()
            if row is None:
                raise ActionNotFoundError("Alert not found.")
            if row["read_at"] is None:
                conn.execute('UPDATE alerts SET read_at=? WHERE id=?', (_iso(now), alert_id))
            return dict(conn.execute('SELECT * FROM alerts WHERE id=?', (alert_id,)).fetchone())

    # ---- stored morning briefings ----------------------------------------------------------------
    def save_briefing_run(self, run_key, payload, trigger, now=None):
        """Store one briefing per run key (e.g. one per day); returns (run, created)."""
        now = now or now_sg()
        run_id = str(uuid4())
        with self.store.connection() as conn:
            created = conn.execute('INSERT OR IGNORE INTO briefing_runs (id, run_key, as_of_date, trigger, generated_at, '
                                   'payload) VALUES (?,?,?,?,?,?)',
                                   (run_id, run_key, payload["briefing"]["as_of_date"], trigger, _iso(now),
                                    json.dumps(payload, ensure_ascii=False))).rowcount
            if created:
                self._audit(conn, "scheduler" if trigger == "scheduler" else "user", "briefing_generated", now,
                            target_kind="briefing", target_id=run_id, detail={"run_key": run_key})
            row = conn.execute('SELECT id, run_key, as_of_date, trigger, generated_at FROM briefing_runs WHERE run_key=?',
                               (run_key,)).fetchone()
        return dict(row), bool(created)

    def list_briefing_runs(self, limit=30):
        with self.store.connection() as conn:
            rows = conn.execute('SELECT id, run_key, as_of_date, trigger, generated_at FROM briefing_runs '
                                'ORDER BY generated_at DESC LIMIT ?', (limit,)).fetchall()
        return [dict(row) for row in rows]

    # ---- one view for the agent and the sidebar ------------------------------------------------
    def follow_ups(self, kind=None):
        everything = {
            "pending_proposals": lambda: self.list_proposals(status="PROPOSED", limit=20),
            "reminders": lambda: [r for r in self.list_reminders() if r["status"] != "DISMISSED"][:20],
            "notes": lambda: self.list_notes()[:20],
            "chase_drafts": lambda: self.list_drafts()[:20],
            "watches": lambda: [w for w in self.list_watches() if w["status"] in ("ACTIVE", "PAUSED", "TRIGGERED")][:20],
            "unread_alerts": lambda: self.list_alerts(unread_only=True, limit=20),
        }
        if kind is not None and kind not in everything:
            raise ValueError(f"kind must be one of {', '.join(everything)}.")
        picked = {kind: everything[kind]} if kind else everything
        return {name: load() for name, load in picked.items()}

    def counts(self):
        with self.store.connection() as conn:
            def one(query):
                return conn.execute(query).fetchone()[0]
            return {
                "pending_proposals": one("SELECT COUNT(*) FROM action_proposals WHERE status='PROPOSED'"),
                "due_reminders": one("SELECT COUNT(*) FROM reminders WHERE status='DUE'"),
                "active_watches": one("SELECT COUNT(*) FROM watches WHERE status='ACTIVE'"),
                "unread_alerts": one("SELECT COUNT(*) FROM alerts WHERE read_at IS NULL"),
            }
