"""Lost responses and failed chat turns must not leave duplicate or confirmable orphan actions."""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from langchain_core.messages import AIMessage
from langgraph.errors import GraphRecursionError

from action_tools import propose_order_note
from actions import ActionStateError, ActionStore, SCHEMA, now_sg
from service import AgentIncompleteError, ChatService
from storage import ConversationConflictError, SQLiteStore
from tests.test_chat_actions import make


def actions_for(tmp_path):
    store = SQLiteStore(tmp_path / 'retry.db')
    store.setup()
    actions = ActionStore(store)
    actions.setup()
    return store, actions


@pytest.mark.parametrize('kind,payload', [
    ('reminder', {'order_id': 'ORD-107', 'text': 'Follow up', 'when': 'tomorrow 09:00'}),
    ('watch', {'order_id': 'ORD-107', 'condition': 'completed'}),
])
def test_api_retries_create_and_confirm_return_one_action(tmp_path, kind, payload):
    _, client = make(tmp_path, [])
    body = {'kind': kind, 'payload': payload, 'request_id': 'one-user-intent'}
    first = client.post('/actions/proposals', json=body).json()
    # The first response can be lost. Sending the same body again must recover its ID.
    second = client.post('/actions/proposals', json=body).json()
    assert first['id'] == second['id']
    client.post(f"/actions/{first['id']}/confirm")
    # A confirmation can succeed even when its response never reaches the browser.
    third = client.post('/actions/proposals', json=body).json()
    assert third['id'] == first['id'] and third['status'] == 'EXECUTED'
    replay = client.post(f"/actions/{third['id']}/confirm").json()
    assert replay['already_done'] is True
    assert len(client.get('/reminders' if kind == 'reminder' else '/watches').json()) == 1
    assert sum(e['event'] == 'executed' for e in client.get('/audit').json()) == 1


def test_request_id_reuse_with_changed_payload_is_rejected(tmp_path):
    _, client = make(tmp_path, [])
    body = {'kind': 'note', 'payload': {'order_id': 'ORD-107', 'text': 'First'}, 'request_id': 'one-intent'}
    assert client.post('/actions/proposals', json=body).status_code == 201
    body['payload']['text'] = 'Changed'
    response = client.post('/actions/proposals', json=body)
    assert response.status_code == 409 and response.json()['code'] == 'ACTION_STATE'
    body['request_id'] = 'edited-intent'
    assert client.post('/actions/proposals', json=body).status_code == 201


def test_concurrent_create_retries_and_time_relative_retry_are_stable(tmp_path):
    _, actions = actions_for(tmp_path)
    payload = {'order_id': 'ORD-107', 'text': 'Follow up', 'when': 'tomorrow 09:00'}
    now = now_sg()
    with ThreadPoolExecutor(max_workers=4) as pool:
        proposals = list(pool.map(lambda _: actions.propose('reminder', payload, 'ui', now=now,
                                                          request_id='same-request'), range(4)))
    assert len({p['id'] for p in proposals}) == 1
    retried = actions.propose('reminder', payload, 'ui', now=now + timedelta(days=1), request_id='same-request')
    assert retried['payload']['remind_at'] == proposals[0]['payload']['remind_at']
    assert len(actions.list_proposals()) == 1


def test_schema_migration_preserves_old_proposals(tmp_path):
    store = SQLiteStore(tmp_path / 'old.db')
    store.setup()
    with store.connection() as conn:
        conn.execute(SCHEMA[0])
        conn.execute('INSERT INTO action_proposals '
                     '(id,kind,status,source,payload,summary,created_at,expires_at) VALUES (?,?,?,?,?,?,?,?)',
                     ('old-note', 'note', 'PROPOSED', 'ui', json.dumps({'order_id': 'ORD-107', 'text': 'Old'}),
                      'Old note', now_sg().isoformat(), (now_sg() + timedelta(hours=1)).isoformat()))
    actions = ActionStore(store)
    actions.setup()
    actions.setup()
    old = actions.get('old-note')
    assert old['payload']['text'] == 'Old' and old['request_id'] is None
    assert actions.confirm('old-note')['result']['text'] == 'Old'


def test_draft_cannot_be_confirmed_or_listed_until_conversation_commit(tmp_path):
    store, actions = actions_for(tmp_path)
    session = store.create_session()['id']
    p = actions.propose('note', {'order_id': 'ORD-107', 'text': 'Draft'}, 'chat', session, turn_id='turn-1')
    assert p['status'] == 'DRAFT' and actions.list_proposals() == []
    with pytest.raises(ActionStateError):
        actions.confirm(p['id'])
    store.update_turn(session, lambda history: (history, 'saved'),
                      on_commit=lambda conn: actions.activate_turn(conn, 'turn-1'))
    assert actions.get(p['id'])['status'] == 'PROPOSED'
    assert actions.confirm(p['id'])['result']['text'] == 'Draft'


def test_conversation_and_proposal_activation_roll_back_together(tmp_path):
    store, actions = actions_for(tmp_path)
    session = store.create_session()['id']
    p = actions.propose('note', {'order_id': 'ORD-107', 'text': 'Draft'}, 'chat', session, turn_id='turn-rollback')

    def fail_after_activation(conn):
        actions.activate_turn(conn, 'turn-rollback')
        raise RuntimeError('Simulated failure before transaction commit')

    messages = [{'type': 'human', 'data': {'content': 'Create note'}}]
    with pytest.raises(RuntimeError):
        store.update_turn(session, lambda history: (messages, 'answer'), on_commit=fail_after_activation)
    assert store.get_history(session) == []
    assert actions.get(p['id'])['status'] == 'DRAFT'
    assert not any(event['event'] == 'proposal_ready' for event in actions.list_audit())
    with pytest.raises(ActionStateError):
        actions.confirm(p['id'])
    actions.fail_turn('turn-rollback')
    assert actions.get(p['id'])['status'] == 'FAILED'


def test_failed_chat_invalidates_only_its_drafts_and_retry_has_one_valid_proposal(tmp_path):
    store, actions = actions_for(tmp_path)
    existing = actions.propose('reminder', {'text': 'Keep this', 'when': 'tomorrow 09:00'}, 'ui')
    actions.confirm(existing['id'])
    captured = []

    class Agent:
        fail = True

        def invoke(self, state, config):
            result = propose_order_note('ORD-107', 'New note')
            captured.append(result['proposal']['id'])
            assert actions.get(captured[-1])['status'] == 'DRAFT'
            with pytest.raises(ActionStateError):
                actions.confirm(captured[-1])
            if self.fail:
                raise GraphRecursionError('simulated failure after tool')
            return {'messages': state['messages'] + [AIMessage(content='A note is ready for review.')]}

    agent = Agent()
    service = ChatService(store, agent=agent)
    session = service.create_session()['id']
    with pytest.raises(AgentIncompleteError):
        service.send_message(session, 'Create a note')
    assert service.get_history(session) == []
    assert actions.get(captured[0])['status'] == 'FAILED'
    assert actions.list_proposals(status='PROPOSED') == []
    with pytest.raises(ActionStateError):
        actions.confirm(captured[0])
    agent.fail = False
    service.send_message(session, 'Create a note')
    assert [p['id'] for p in actions.list_proposals(status='PROPOSED')] == [captured[1]]
    assert len(actions.list_reminders()) == 1
    assert actions.get(existing['id'])['status'] == 'EXECUTED'
    assert any(e['event'] == 'turn_failed' for e in actions.list_audit())


def test_conversation_conflict_invalidates_losing_turn_draft(tmp_path):
    store, actions = actions_for(tmp_path)
    session = store.create_session()['id']
    captured = []

    class Agent:
        def invoke(self, state, config):
            result = propose_order_note('ORD-107', 'Losing turn')
            captured.append(result['proposal']['id'])
            store.update_turn(session, lambda history: (history, 'another request won'))
            return {'messages': state['messages'] + [AIMessage(content='Ready for review.')]}

    service = ChatService(store, agent=Agent())
    with pytest.raises(ConversationConflictError):
        service.send_message(session, 'Create a note')
    assert actions.get(captured[0])['status'] == 'FAILED'
    assert actions.list_proposals(status='PROPOSED') == []
    assert actions.list_notes() == []
