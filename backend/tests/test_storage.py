"""SQLite session store: persistence, rollback and concurrent-turn protection."""

import pytest

from storage import SQLiteStore


@pytest.fixture
def store(tmp_path):
    store = SQLiteStore(tmp_path / "app.db")
    store.setup()
    return store


def human(text):
    """Same shape as langchain_core messages_to_dict output."""
    return {"type": "human", "data": {"content": text}}


def test_session_round_trip(store):
    session = store.create_session("Morning check")
    assert store.list_sessions()[0]["id"] == session["id"]
    assert store.get_history(session["id"]) == []

    answer = store.update_turn(session["id"], lambda saved: (saved + [human("hi")], "ok"))
    assert answer == "ok"
    assert store.get_history(session["id"]) == [human("hi")]


def test_untitled_session_is_named_after_first_question(store):
    session_id = store.create_session()["id"]
    listed = store.list_sessions()[0]
    assert (listed["title"], listed["has_messages"]) == ("New conversation", False)
    store.update_turn(session_id, lambda saved: (saved + [human("  Which   orders are late? ")], "ok"))
    listed = store.list_sessions()[0]
    assert (listed["title"], listed["has_messages"]) == ("Which orders are late?", True)


def test_given_title_is_kept(store):
    session_id = store.create_session("Morning check")["id"]
    store.update_turn(session_id, lambda saved: (saved + [human("Which orders are late?")], "ok"))
    assert store.list_sessions()[0]["title"] == "Morning check"


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
        store.update_turn(session_id, lambda inner: (inner + [human("other")], "other"))
        return saved + [human("mine")], "mine"

    with pytest.raises(ValueError):
        store.update_turn(session_id, slow_turn)
    assert store.get_history(session_id) == [human("other")]


def test_unknown_session(store):
    with pytest.raises(KeyError):
        store.get_history("missing")
    with pytest.raises(KeyError):
        store.update_turn("missing", lambda saved: (saved, "x"))


def test_title_validation(store):
    with pytest.raises(ValueError):
        store.create_session("   ")
