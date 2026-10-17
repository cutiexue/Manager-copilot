"""Store completed conversation turns in a local SQLite file (application state only)."""

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from config import read_env

DEFAULT_DB = Path(__file__).resolve().with_name('manager_copilot.db')


class SQLiteStore:
    def __init__(self, path=None):
        values = read_env(Path(__file__).with_name('.env'))
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

    def create_session(self, title='New conversation'):
        if not isinstance(title, str) or not title.strip() or len(title) > 200:
            raise ValueError('Title must contain 1 to 200 characters.')
        session_id = str(uuid4())
        with self.connection() as conn:
            conn.execute('INSERT INTO assistant_sessions (id, title, messages) VALUES (?,?,?)',
                         (session_id, title.strip(), '[]'))
        return {'id': session_id, 'title': title.strip()}

    def list_sessions(self):
        with self.connection() as conn:
            rows = conn.execute('SELECT id,title,created_at,updated_at FROM assistant_sessions '
                                'ORDER BY updated_at DESC,id').fetchall()
            return [dict(row) for row in rows]

    def get_history(self, session_id):
        with self.connection() as conn:
            row = conn.execute('SELECT messages FROM assistant_sessions WHERE id=?',
                               (session_id,)).fetchone()
            if row is None:
                raise KeyError('Session not found.')
            return json.loads(row['messages'])

    def update_turn(self, session_id, generate):
        # SQLite 只有一个写锁；模型调用可能长达一分钟，不能在调用期间占住整个数据库。
        # 因此先读出版本号，生成回答后按版本号条件更新：同一会话被并发修改时本轮失败，不会互相覆盖。
        with self.connection() as conn:
            row = conn.execute('SELECT messages,version FROM assistant_sessions WHERE id=?',
                               (session_id,)).fetchone()
        if row is None:
            raise KeyError('Session not found.')
        messages, answer = generate(json.loads(row['messages']))
        with self.connection() as conn:
            updated = conn.execute(
                'UPDATE assistant_sessions SET messages=?,version=version+1,'
                'updated_at=CURRENT_TIMESTAMP WHERE id=? AND version=?',
                (json.dumps(messages, ensure_ascii=False, allow_nan=False), session_id, row['version']))
            if updated.rowcount != 1:
                raise ValueError('This conversation changed during the request; send the message again.')
        return answer
