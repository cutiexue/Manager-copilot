"""Chat request IDs recover committed responses without a second model turn or proposal."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
import sqlite3
import threading
import time

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.errors import GraphRecursionError
import pytest

from action_tools import propose_order_note
from actions import now_sg
from api import create_app
from service import ChatService
from storage import RequestInProgressError, SQLiteStore
from tests.test_chat_actions import call, make


def service_for(tmp_path, agent):
    store = SQLiteStore(tmp_path / 'chat-retry.db')
    store.setup()
    service = ChatService(store, agent=agent)
    return service, TestClient(create_app(service))


def test_lost_response_replays_one_committed_turn_after_restart(tmp_path):
    service, client = make(tmp_path, [
        call('propose_reminder', {'order_id': 'ORD-107', 'text': 'Follow up', 'when': 'tomorrow 09:00'}, 'c1'),
        AIMessage(content='The reminder is ready for confirmation.'),
    ])
    session = client.post('/sessions', json={'title': 'Retry', 'request_id': 'create-once'}).json()
    # Losing the creation response also recovers the same conversation.
    assert client.post('/sessions', json={'title': 'Retry', 'request_id': 'create-once'}).json() == session
    assert len(service.list_sessions()) == 1
    route = f"/sessions/{session['id']}/messages"
    body = {'message': 'Prepare a reminder', 'request_id': 'logical-send'}
    first = client.post(route, json=body)
    assert first.status_code == 200
    original = first.json()
    assert original['proposals'][0]['status'] == 'PROPOSED'
    assert service.actions.list_reminders() == []
    # Pretend the successful response was lost; no script/model calls remain.
    assert client.post(route, json=body).json() == original
    restarted = ChatService(service.store, agent=object())
    assert restarted.send_message(session['id'], body['message'], body['request_id']) == original
    assert len(service.get_history(session['id'])) == 2
    assert len(service.actions.list_proposals()) == 1
    proposal = original['proposals'][0]['id']
    client.post(f'/actions/{proposal}/confirm')
    assert client.post(f'/actions/{proposal}/confirm').json()['already_done'] is True
    assert len(service.actions.list_reminders()) == 1
    replay = restarted.send_message(session['id'], body['message'], body['request_id'])
    assert replay['proposals'][0]['status'] == 'EXECUTED'
    assert replay['proposals'][0]['id'] == proposal
    assert {k: v for k, v in replay.items() if k != 'proposals'} == {
        k: v for k, v in original.items() if k != 'proposals'}
    assert len(service.get_history(session['id'])) == 2
    assert len(service.actions.list_reminders()) == 1


@pytest.mark.parametrize('new_state', ['CANCELLED', 'EXPIRED'])
def test_replay_refreshes_closed_card_without_changing_recorded_answer(tmp_path, new_state):
    service, client = make(tmp_path, [
        call('propose_order_note', {'order_id': 'ORD-107', 'text': 'Follow up'}, 'c1'),
        AIMessage(content='The note is ready for confirmation.'),
    ])
    session = service.create_session()['id']
    original = service.send_message(session, 'Prepare a note', 'one-note')
    proposal_id = original['proposals'][0]['id']
    if new_state == 'CANCELLED':
        service.actions.cancel(proposal_id)
    else:
        service.actions.expire_stale(now_sg() + timedelta(days=2))
    # No scripted model responses remain: replay must only read the saved turn.
    replay = service.send_message(session, 'Prepare a note', 'one-note')
    assert replay['proposals'][0]['status'] == new_state
    assert replay['proposals'][0]['id'] == proposal_id
    assert {k: v for k, v in replay.items() if k != 'proposals'} == {
        k: v for k, v in original.items() if k != 'proposals'}
    assert len(service.get_history(session)) == 2
    assert len(service.actions.list_proposals()) == 1
    assert service.actions.list_notes() == []


def test_response_commit_failure_rolls_back_history_and_activation_then_allows_retry(tmp_path, monkeypatch):
    class Agent:
        def invoke(self, state, config):
            return {'messages': note_messages(state, 'Follow up')}

    service, _ = service_for(tmp_path, Agent())
    session = service.create_session()['id']
    original_complete = service.store.complete_chat_request

    def fail_after_save(conn, claim, response):
        original_complete(conn, claim, response)
        raise RuntimeError('simulated final commit failure')

    monkeypatch.setattr(service.store, 'complete_chat_request', fail_after_save)
    with pytest.raises(RuntimeError, match='simulated final commit failure'):
        service.send_message(session, 'Prepare a note', 'retry-commit')
    assert service.get_history(session) == []
    assert [p['status'] for p in service.actions.list_proposals()] == ['FAILED']
    assert service.actions.list_notes() == []
    monkeypatch.setattr(service.store, 'complete_chat_request', original_complete)
    reply = service.send_message(session, 'Prepare a note', 'retry-commit')
    assert reply['proposals'][0]['status'] == 'PROPOSED'
    assert len(service.get_history(session)) == 2


def test_additive_setup_keeps_legacy_history_and_supports_request_ids(tmp_path):
    path = tmp_path / 'legacy.db'
    history = [{'type': 'human', 'data': {'content': 'Earlier question'}}]
    with sqlite3.connect(path) as conn:
        conn.execute('''CREATE TABLE assistant_sessions (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, messages TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
        conn.execute('INSERT INTO assistant_sessions(id,title,messages) VALUES (?,?,?)',
                     ('legacy', 'Earlier conversation', json.dumps(history)))
    store = SQLiteStore(path)
    store.setup()
    store.setup()  # repeat startup migrations are also safe
    assert store.get_history('legacy') == history
    assert store.list_sessions()[0]['title'] == 'Earlier conversation'
    first = store.create_session('New', 'create-once')
    assert store.create_session('New', 'create-once') == first
    assert store.claim_chat_request('legacy', 'new-turn', 'Hello', 'owner')['owner_token'] == 'owner'


def test_changed_content_with_same_request_id_is_rejected(tmp_path):
    service, client = make(tmp_path, [AIMessage(content='Hello.')])
    session = client.post('/sessions', json={'title': 'Original', 'request_id': 'create-once'}).json()
    conflict = client.post('/sessions', json={'title': 'Different', 'request_id': 'create-once'})
    assert (conflict.status_code, conflict.json()['code']) == (409, 'REQUEST_CONFLICT')
    route = f"/sessions/{session['id']}/messages"
    assert client.post(route, json={'message': 'Hello', 'request_id': 'same'}).status_code == 200
    conflict = client.post(route, json={'message': 'Different', 'request_id': 'same'})
    assert (conflict.status_code, conflict.json()['code']) == (409, 'REQUEST_CONFLICT')
    assert len(service.get_history(session['id'])) == 2


def test_concurrent_http_duplicate_never_calls_model_twice(tmp_path):
    entered, release = threading.Event(), threading.Event()

    class Agent:
        calls = 0

        def invoke(self, state, config):
            self.calls += 1
            entered.set()
            assert release.wait(5)
            return {'messages': state['messages'] + [AIMessage(content='Hello.')]}

    agent = Agent()
    service, client = service_for(tmp_path, agent)
    session = service.create_session()['id']
    route = f'/sessions/{session}/messages'
    body = {'message': 'Hello', 'request_id': 'concurrent'}
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(client.post, route, json=body)
        assert entered.wait(5)
        try:
            duplicate = client.post(route, json=body)
            assert (duplicate.status_code, duplicate.json()['code']) == (409, 'REQUEST_IN_PROGRESS')
            # No write transaction is held while the model waits.
            service.create_session('Another conversation remains writable')
        finally:
            release.set()
        result = first.result(timeout=5)
    assert result.status_code == 200
    assert client.post(route, json=body).json() == result.json()
    assert agent.calls == 1 and len(service.get_history(session)) == 2


def note_messages(state, text):
    result = propose_order_note('ORD-107', text)
    return state['messages'] + [
        call('propose_order_note', {'order_id': 'ORD-107', 'text': text}, 'note-call'),
        ToolMessage(content=json.dumps(result), name='propose_order_note', tool_call_id='note-call'),
        AIMessage(content='The note is ready for confirmation.'),
    ]


def test_failed_turn_releases_request_for_same_intent_and_invalidates_its_draft(tmp_path):
    class Agent:
        fail = True

        def invoke(self, state, config):
            messages = note_messages(state, 'Follow up')
            if self.fail:
                raise GraphRecursionError('simulated failure after proposal')
            return {'messages': messages}

    agent = Agent()
    service, client = service_for(tmp_path, agent)
    session = service.create_session()['id']
    route = f'/sessions/{session}/messages'
    body = {'message': 'Add a note', 'request_id': 'recoverable'}
    assert client.post(route, json=body).status_code == 502
    assert service.get_history(session) == []
    assert [p['status'] for p in service.actions.list_proposals()] == ['FAILED']
    assert service.actions.list_notes() == []
    # Failure preserves the fingerprint, so the ID cannot be recycled for another intent.
    assert client.post(route, json={**body, 'message': 'Different'}).status_code == 409
    agent.fail = False
    retried = client.post(route, json=body)
    assert retried.status_code == 200
    assert len(service.get_history(session)) == 2
    assert len(service.actions.list_proposals(status='PROPOSED')) == 1
    assert service.actions.list_notes() == []


def test_conversation_conflict_does_not_permanently_block_request_retry(tmp_path):
    class Agent:
        conflict = True

        def invoke(self, state, config):
            messages = note_messages(state, 'New note')
            if self.conflict:
                self.conflict = False
                service.store.update_turn(session, lambda saved: (saved, 'other turn'))
            return {'messages': messages}

    service, client = service_for(tmp_path, Agent())
    session = service.create_session()['id']
    route = f'/sessions/{session}/messages'
    body = {'message': 'Add a note', 'request_id': 'conflict-retry'}
    failed = client.post(route, json=body)
    assert (failed.status_code, failed.json()['code']) == (409, 'CONFLICT')
    assert len(service.actions.list_proposals(status='FAILED')) == 1
    assert client.post(route, json=body).status_code == 200
    assert len(service.actions.list_proposals(status='PROPOSED')) == 1
    assert len(service.get_history(session)) == 2


def test_stale_owner_cannot_commit_release_or_renew_new_claim(tmp_path):
    service, _ = service_for(tmp_path, object())
    store = service.store
    session = service.create_session()['id']
    old = store.claim_chat_request(session, 'same', 'Hello', 'old-owner')
    with store.connection() as conn:
        conn.execute('UPDATE chat_requests SET lease_until=0')
    new = store.claim_chat_request(session, 'same', 'Hello', 'new-owner')
    assert new['abandoned_turn'] == 'old-owner'
    assert store.renew_chat_request(old) is False
    store.fail_chat_request(old)
    with pytest.raises(RequestInProgressError):
        store.claim_chat_request(session, 'same', 'Hello', 'third-owner')
    with pytest.raises(RequestInProgressError):
        store.update_turn(session, lambda saved: ([{'old': 'must not persist'}], 'old answer'),
                          on_commit=lambda conn: store.complete_chat_request(conn, old, {'answer': 'old'}))
    assert store.get_history(session) == []
    store.update_turn(session, lambda saved: (saved, 'new answer'),
                      on_commit=lambda conn: store.complete_chat_request(conn, new, {'answer': 'new'}))
    assert store.claim_chat_request(session, 'same', 'Hello', 'replay')['response'] == {'answer': 'new'}


def test_lease_heartbeat_protects_a_slow_turn(tmp_path, monkeypatch):
    service, _ = service_for(tmp_path, object())
    store = service.store
    monkeypatch.setattr(store, 'CHAT_LEASE_SECONDS', 0.2)
    monkeypatch.setattr(store, 'CHAT_HEARTBEAT_SECONDS', 0.02)
    session = service.create_session()['id']
    claim = store.claim_chat_request(session, 'slow', 'Hello', 'owner')
    with store.keep_chat_request_alive(claim):
        time.sleep(0.3)  # longer than the initial lease, with no model or network call
        with pytest.raises(RequestInProgressError):
            store.claim_chat_request(session, 'slow', 'Hello', 'duplicate')
    store.fail_chat_request(claim)
    assert store.claim_chat_request(session, 'slow', 'Hello', 'retry')['owner_token'] == 'retry'


def test_expired_worker_drafts_are_invalidated_before_recovery(tmp_path):
    service, client = service_for(tmp_path, type('Agent', (), {
        'invoke': lambda self, state, config: {'messages': state['messages'] + [AIMessage(content='Recovered.')]}
    })())
    session = service.create_session()['id']
    service.store.claim_chat_request(session, 'recover', 'Hello', 'crashed-turn')
    draft = service.actions.propose('note', {'order_id': 'ORD-107', 'text': 'Old draft'}, 'chat',
                                    session_id=session, turn_id='crashed-turn')
    with service.store.connection() as conn:
        conn.execute('UPDATE chat_requests SET lease_until=0')
    reply = client.post(f'/sessions/{session}/messages', json={'message': 'Hello', 'request_id': 'recover'})
    assert reply.status_code == 200
    assert service.actions.get(draft['id'])['status'] == 'FAILED'
    assert service.actions.list_proposals(status='PROPOSED') == []
    assert service.actions.list_notes() == []


@pytest.mark.parametrize('request_id', ['', 'x/y', 4, 'x' * 129])
def test_invalid_request_ids_are_rejected_before_model(tmp_path, request_id):
    service, client = service_for(tmp_path, object())
    session = service.create_session()['id']
    response = client.post(f'/sessions/{session}/messages', json={'message': 'Hello', 'request_id': request_id})
    assert response.status_code == 400
    assert service.get_history(session) == []
