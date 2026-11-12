"""A turn's data and historical evidence stay pinned while the app advances snapshots."""

import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, messages_to_dict

import evidence_refs
import rules
from service import ChatService
from tests.test_chat_actions import ScriptedModel, call, make
from tools import get_order_status
from views import NotFoundError, evidence_row
import pytest


def order_evidence(reply):
    ref = next(r for r in reply['evidence']['refs'] if r['key'] == 'ORD-107')
    return ref, reply['evidence']['rows'][ref['row_key']]


def test_one_agent_turn_stays_on_one_snapshot_including_tool_worker_threads(tmp_path, monkeypatch):
    original = ScriptedModel._generate
    switched = []

    def changing_snapshot(self, messages, stop=None, run_manager=None, **kwargs):
        # The first tool has completed; the app changes snapshots before the next tool runs.
        if sum(m.type == 'tool' for m in messages) == 1 and not switched:
            service.actions.set_data_version('v1')
            switched.append(True)
        return original(self, messages, stop, run_manager, **kwargs)

    monkeypatch.setattr(ScriptedModel, '_generate', changing_snapshot)
    service, client = make(tmp_path, [
        call('get_order_status', {'order_id': 'ORD-107'}, 'c1'),
        call('get_order_status', {'order_id': 'ORD-107'}, 'c2'),
        AIMessage(content='ORD-107 is in progress.'),
        call('get_order_status', {'order_id': 'ORD-107'}, 'c3'),
        AIMessage(content='ORD-107 is complete.'),
    ])
    session = service.create_session()['id']
    first = client.post(f'/sessions/{session}/messages', json={'message': 'Check ORD-107 twice.'}).json()
    assert switched
    assert rules.current_version() == 'v1'
    assert first['evidence']['data_version'] == 'v0'
    assert first['evidence']['data_date'] == '2026-04-01'
    assert [c['result']['data']['status'] for c in first['tool_calls']] == ['IN_PROGRESS', 'IN_PROGRESS']
    ref, row = order_evidence(first)
    assert ref['id'].endswith('@v0') and row['status'] == 'IN_PROGRESS'

    second = client.post(f'/sessions/{session}/messages', json={'message': 'Check ORD-107 now.'}).json()
    assert second['evidence']['data_version'] == 'v1'
    assert second['evidence']['data_date'] == '2026-04-02'
    assert order_evidence(second)[1]['status'] == 'COMPLETE'

    history = client.get(f'/sessions/{session}/messages').json()
    assert history[1]['evidence'] == first['evidence']
    assert history[3]['evidence'] == second['evidence']
    assert history[1]['answer_check'] == first['answer_check']

    # A restarted service reads the saved v1 app state, but the first turn retains its actual rows.
    restarted = ChatService(service.store, agent=object())
    assert rules.current_version() == 'v1'
    assert restarted.get_history(session)[1]['evidence'] == first['evidence']

    def no_current_data(*args, **kwargs):
        raise AssertionError('History must use its saved rows, not read current CSVs')

    monkeypatch.setattr(evidence_refs, 'raw_rows', no_current_data)
    monkeypatch.setattr(evidence_refs, 'order_row_numbers', no_current_data)
    assert restarted.get_history(session)[1]['evidence'] == first['evidence']


def test_legacy_chat_does_not_substitute_current_rows_for_unknown_historical_version(tmp_path):
    service, _ = make(tmp_path, [])
    session = service.create_session()['id']
    result = get_order_status('ORD-107')
    messages = [HumanMessage(content='Check ORD-107'),
                call('get_order_status', {'order_id': 'ORD-107'}, 'old-call'),
                ToolMessage(content=json.dumps(result), tool_call_id='old-call', name='get_order_status'),
                AIMessage(content='ORD-107 is in progress.')]
    service.store.update_turn(session, lambda saved: (messages_to_dict(messages), messages[-1].content))
    service.actions.set_data_version('v1')
    answer = service.get_history(session)[-1]
    assert answer['evidence']['rows'] == {}
    assert answer['evidence']['source_context'] == 'legacy_unknown'
    assert answer['evidence']['warnings']
    assert answer['tool_calls'][0]['result']['data']['status'] == 'IN_PROGRESS'
    assert answer['answer_check']['unavailable'] is True


def test_two_versions_of_one_row_have_distinct_refs_and_evidence_keys():
    rows = evidence_refs.collect([
        {'data_version': 'v0', 'source': 'track1/data/orders.csv', 'row': 81, 'key': 'ORD-107'},
        {'data_version': 'v1', 'source': 'track1/data/orders.csv', 'row': 81, 'key': 'ORD-107'},
    ], versioned=True)
    assert len(rows) == 2
    assert len({r['id'] for r in rows}) == len({r['row_key'] for r in rows}) == 2
    evidence = evidence_refs.raw_rows(rows)
    assert evidence[rows[0]['row_key']]['status'] == 'IN_PROGRESS'
    assert evidence[rows[1]['row_key']]['status'] == 'COMPLETE'


def test_versioned_evidence_endpoint_and_legacy_ids_are_both_supported():
    rules.set_current_data('v1', '2026-04-02')
    assert evidence_row('orders.csv:81@v0')['data']['status'] == 'IN_PROGRESS'
    assert evidence_row('orders.csv:81@v1')['data']['status'] == 'COMPLETE'
    assert evidence_row('orders.csv:81')['data']['status'] == 'COMPLETE'
    with pytest.raises(NotFoundError):
        evidence_row('orders.csv:81@v999')


def test_data_context_restores_after_an_exception():
    with pytest.raises(RuntimeError), rules.data_context('v0', '2026-04-01'):
        rules.set_current_data('v1', '2026-04-02')
        assert rules.current_version() == 'v0'
        assert rules.today_iso() == '2026-04-01'
        raise RuntimeError('stop')
    assert rules.current_version() == 'v1'
    assert rules.today_iso() == '2026-04-02'
