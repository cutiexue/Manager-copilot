"""Store completed conversation turns in a dedicated local MySQL database."""

import json
import os
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pymysql
from config import read_env


class MySQLStore:
    def __init__(self, password=None):
        values = read_env(Path(__file__).with_name('.env'))
        values.update(os.environ)
        self.options = dict(
            host=values.get('MYSQL_HOST', 'localhost'),
            port=int(values.get('MYSQL_PORT', '3306')),
            user=values.get('MYSQL_USER', 'dss5105_app'),
            password=password if password is not None else values.get('MYSQL_PASSWORD', ''),
            database=values.get('MYSQL_DATABASE', 'dss5105'),
            charset='utf8mb4', autocommit=False, connect_timeout=5,
            cursorclass=pymysql.cursors.DictCursor,
        )
        if not self.options['password']:
            raise ValueError('Set MYSQL_PASSWORD locally or enter it at startup.')

    @contextmanager
    def connection(self):
        conn = pymysql.connect(**self.options)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def setup(self):
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute('''CREATE TABLE IF NOT EXISTS assistant_sessions (
                id CHAR(36) PRIMARY KEY,
                title VARCHAR(200) NOT NULL,
                messages LONGTEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4''')

    def create_session(self, title='New conversation'):
        if not isinstance(title, str) or not title.strip() or len(title) > 200:
            raise ValueError('Title must contain 1 to 200 characters.')
        session_id = str(uuid4())
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute('INSERT INTO assistant_sessions (id, title, messages) VALUES (%s,%s,%s)',
                        (session_id, title.strip(), '[]'))
        return {'id': session_id, 'title': title.strip()}

    def list_sessions(self):
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute('SELECT id,title,created_at,updated_at FROM assistant_sessions ORDER BY updated_at DESC,id')
            return cur.fetchall()

    def get_history(self, session_id):
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute('SELECT messages FROM assistant_sessions WHERE id=%s', (session_id,))
            row = cur.fetchone()
            if row is None:
                raise KeyError('Session not found.')
            return json.loads(row['messages'])

    def update_turn(self, session_id, generate):
        # 行锁避免两个入口同时覆盖同一个会话；不同会话可独立执行。
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute('SELECT messages FROM assistant_sessions WHERE id=%s FOR UPDATE', (session_id,))
            row = cur.fetchone()
            if row is None:
                raise KeyError('Session not found.')
            messages, answer = generate(json.loads(row['messages']))
            cur.execute('UPDATE assistant_sessions SET messages=%s,updated_at=CURRENT_TIMESTAMP WHERE id=%s',
                        (json.dumps(messages, ensure_ascii=False, allow_nan=False), session_id))
            return answer
