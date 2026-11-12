"""Store completed conversation turns in a local SQLite file (application state only)."""

import hashlib
import json
import os
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from config import read_env
from paths import DEFAULT_DB, ENV_FILE


class SessionNotFoundError(KeyError):
    """No conversation has this ID. A KeyError subclass, so older callers keep working."""


class ConversationConflictError(ValueError):
    """The conversation changed while this turn was generated; nothing was saved."""


class RequestConflictError(ValueError):
    """A request ID was reused for different content."""


class RequestInProgressError(ValueError):
    """The same logical turn is still running, or this worker lost its claim."""


def _request_id(value):
    if value is not None and (not isinstance(value, str) or
                              not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', value)):
        raise ValueError('request_id must be 1 to 128 letters, digits, dots, underscores, colons or hyphens.')
    return value


def _fingerprint(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


class SQLiteStore:
    # Long model calls renew a short-lived claim; a crashed worker cannot block retries forever.
    CHAT_LEASE_SECONDS = 300
    CHAT_HEARTBEAT_SECONDS = 30

    def __init__(self, path=None):
        values = read_env(ENV_FILE)
        values.update(os.environ)
        self.path = Path(path or values.get('SQLITE_PATH') or DEFAULT_DB)

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def setup(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS assistant_sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                messages TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )''')

            columns = {row['name'] for row in conn.execute('PRAGMA table_info(assistant_sessions)')}
            for name in ('create_request_id', 'create_fingerprint'):
                if name not in columns:
                    conn.execute(f'ALTER TABLE assistant_sessions ADD COLUMN {name} TEXT')
            conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS session_create_request_id '
                         'ON assistant_sessions(create_request_id) WHERE create_request_id IS NOT NULL')
            conn.execute('''CREATE TABLE IF NOT EXISTS chat_requests (
                session_id TEXT NOT NULL,
                request_id TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                status TEXT NOT NULL,
                owner_token TEXT,
                lease_until REAL,
                response TEXT,
                PRIMARY KEY (session_id, request_id)
            )''')

    def create_session(self, title='New conversation', request_id=None):
        if not isinstance(title, str) or not title.strip() or len(title) > 200:
            raise ValueError('Title must contain 1 to 200 characters.')
        _request_id(request_id)
        title = title.strip()
        fingerprint = _fingerprint(title)
        session_id = str(uuid4())
        with self.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            if request_id is not None:
                previous = conn.execute('SELECT id,title,create_fingerprint FROM assistant_sessions '
                                        'WHERE create_request_id=?', (request_id,)).fetchone()
                if previous is not None:
                    if previous['create_fingerprint'] != fingerprint:
                        raise RequestConflictError('This request_id was already used for a different conversation.')
                    return {'id': previous['id'], 'title': previous['title']}
            conn.execute('INSERT INTO assistant_sessions (id,title,messages,create_request_id,create_fingerprint) '
                         'VALUES (?,?,?,?,?)', (session_id, title, '[]', request_id, fingerprint))
        return {'id': session_id, 'title': title}

    def claim_chat_request(self, session_id, request_id, message, owner_token):
        """Reserve a logical send in a short transaction; completed retries replay their response.

        A pending duplicate gets a retryable conflict instead of a second model invocation.
        Owner tokens fence expired workers out of both completion and cleanup.
        """
        if _request_id(request_id) is None:
            return None  # Existing CLI/evaluation clients keep their original API contract.
        fingerprint = _fingerprint(message)
        now = time.time()
        claim = {'session_id': session_id, 'request_id': request_id, 'owner_token': owner_token}
        with self.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            if conn.execute('SELECT 1 FROM assistant_sessions WHERE id=?', (session_id,)).fetchone() is None:
                raise SessionNotFoundError('Session not found.')
            previous = conn.execute('SELECT * FROM chat_requests WHERE session_id=? AND request_id=?',
                                    (session_id, request_id)).fetchone()
            if previous is not None:
                if previous['fingerprint'] != fingerprint:
                    raise RequestConflictError('This request_id was already used for a different message. '
                                               'Use a new request_id when changing the request.')
                if previous['status'] == 'COMPLETED':
                    return {**claim, 'response': json.loads(previous['response'])}
                if previous['status'] == 'RUNNING' and previous['lease_until'] > now:
                    raise RequestInProgressError('This message is still being processed. Retry the same request shortly.')
                if previous['status'] == 'RUNNING':
                    claim['abandoned_turn'] = previous['owner_token']
                conn.execute("UPDATE chat_requests SET status='RUNNING',owner_token=?,lease_until=?,response=NULL "
                             'WHERE session_id=? AND request_id=?',
                             (owner_token, now + self.CHAT_LEASE_SECONDS, session_id, request_id))
            else:
                conn.execute('INSERT INTO chat_requests '
                             '(session_id,request_id,fingerprint,status,owner_token,lease_until) VALUES (?,?,?,?,?,?)',
                             (session_id, request_id, fingerprint, 'RUNNING', owner_token, now + self.CHAT_LEASE_SECONDS))
        return claim

    def renew_chat_request(self, claim):
        now = time.time()
        with self.connection() as conn:
            updated = conn.execute("UPDATE chat_requests SET lease_until=? WHERE session_id=? AND request_id=? "
                                   "AND owner_token=? AND status='RUNNING' AND lease_until>?",
                                   (now + self.CHAT_LEASE_SECONDS, claim['session_id'], claim['request_id'],
                                    claim['owner_token'], now))
            return updated.rowcount == 1

    @contextmanager
    def keep_chat_request_alive(self, claim):
        if claim is None:
            yield
            return
        stopped = threading.Event()

        def heartbeat():
            while not stopped.wait(self.CHAT_HEARTBEAT_SECONDS):
                try:
                    if not self.renew_chat_request(claim):
                        return
                except sqlite3.Error:
                    # Completion still checks the lease and owner under the write transaction.
                    # A transient database failure must not silently grant a stale worker ownership.
                    continue

        thread = threading.Thread(target=heartbeat, name='chat-request-lease', daemon=True)
        thread.start()
        try:
            yield
        finally:
            stopped.set()
            thread.join(timeout=11)

    def complete_chat_request(self, conn, claim, response):
        if claim is None:
            return
        updated = conn.execute("UPDATE chat_requests SET status='COMPLETED',response=?,lease_until=NULL "
                               "WHERE session_id=? AND request_id=? AND owner_token=? AND status='RUNNING' "
                               'AND lease_until>?',
                               (json.dumps(response, ensure_ascii=False, allow_nan=False), claim['session_id'],
                                claim['request_id'], claim['owner_token'], time.time()))
        if updated.rowcount != 1:
            raise RequestInProgressError('This request no longer owns the turn. Retry the same request to recover its result.')

    def fail_chat_request(self, claim):
        if claim is None:
            return
        with self.connection() as conn:
            conn.execute("UPDATE chat_requests SET status='FAILED',lease_until=NULL WHERE session_id=? AND request_id=? "
                         "AND owner_token=? AND status='RUNNING'",
                         (claim['session_id'], claim['request_id'], claim['owner_token']))

    def list_sessions(self):
        with self.connection() as conn:
            rows = conn.execute('SELECT id,title,messages,created_at,updated_at FROM assistant_sessions '
                                'ORDER BY updated_at DESC,id').fetchall()
        sessions = []
        for row in rows:
            session = dict(row)
            messages = json.loads(session.pop('messages'))
            session['has_messages'] = bool(messages)
            if session['title'] == 'New conversation':
                session['title'] = self._title(messages)
            sessions.append(session)
        return sessions

    @staticmethod
    def _title(messages):
        # 未命名会话用第一句提问作标题，方便在历史列表中辨认。
        for message in messages:
            if message.get('type') == 'human':
                content = message.get('data', {}).get('content')
                if isinstance(content, str) and content.strip():
                    return ' '.join(content.split())[:60]
        return 'New conversation'

    def get_history(self, session_id):
        with self.connection() as conn:
            row = conn.execute('SELECT messages FROM assistant_sessions WHERE id=?',
                               (session_id,)).fetchone()
            if row is None:
                raise SessionNotFoundError('Session not found.')
            return json.loads(row['messages'])

    def update_turn(self, session_id, generate, on_commit=None):
        # SQLite 只有一个写锁；模型调用可能长达一分钟，不能在调用期间占住整个数据库。
        # 因此先读出版本号，生成回答后按版本号条件更新：同一会话被并发修改时本轮失败，不会互相覆盖。
        with self.connection() as conn:
            row = conn.execute('SELECT title,messages,version FROM assistant_sessions WHERE id=?',
                               (session_id,)).fetchone()
        if row is None:
            raise SessionNotFoundError('Session not found.')
        messages, answer = generate(json.loads(row['messages']))
        title = self._title(messages) if row['title'] == 'New conversation' else row['title']
        with self.connection() as conn:
            updated = conn.execute(
                'UPDATE assistant_sessions SET messages=?,title=?,version=version+1,'
                'updated_at=CURRENT_TIMESTAMP WHERE id=? AND version=?',
                (json.dumps(messages, ensure_ascii=False, allow_nan=False), title, session_id,
                 row['version']))
            if updated.rowcount != 1:
                raise ConversationConflictError('This conversation changed during the request; send the message again.')
            if on_commit is not None:
                # Activating a turn's drafts and persisting its messages succeed or roll back together.
                on_commit(conn)
        return answer
