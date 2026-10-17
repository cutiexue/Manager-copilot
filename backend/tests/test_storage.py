"""SQLite session store: persistence, rollback and concurrent-turn protection."""

import pytest

from storage import SQLiteStore


@pytest.fixture
def store(tmp_path):
    store = SQLiteStore(tmp_path / "app.db")
    store.setup()
    return store


def test_session_round_trip(store):
    session = store.create_session("Morning check")
    assert store.list_sessions()[0]["id"] == session["id"]
    assert store.get_history(session["id"]) == []

    answer = store.update_turn(session["id"], lambda saved: (saved + [{"type": "human"}], "ok"))
    assert answer == "ok"
    assert store.get_history(session["id"]) == [{"type": "human"}]


def test_failed_turn_leaves_history_unchanged(store):
    session_id = store.create_session()["id"]

    def fail(saved):
        raise RuntimeError("model error")

    with pytest.raises(RuntimeError):
        store.update_turn(session_id, fail)
    assert store.get_history(session_id) == []


def test_concurrent_turn_does_not_overwrite(store):
    session_id = store.create_session()["id"]

    def slow_turn(saved):
        # 模拟本轮模型调用期间，另一个请求先写入了同一会话。
        store.update_turn(session_id, lambda inner: (inner + ["other"], "other"))
        return saved + ["mine"], "mine"

    with pytest.raises(ValueError):
        store.update_turn(session_id, slow_turn)
    assert store.get_history(session_id) == ["other"]


def test_unknown_session(store):
    with pytest.raises(KeyError):
        store.get_history("missing")
    with pytest.raises(KeyError):
        store.update_turn("missing", lambda saved: (saved, "x"))


def test_title_validation(store):
    with pytest.raises(ValueError):
        store.create_session("   ")
