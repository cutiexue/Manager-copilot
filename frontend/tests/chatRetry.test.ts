import assert from 'node:assert/strict';
import test from 'node:test';
import { chatAttemptFor, sendChatAttempt, type ChatAttempt } from '../src/chatRetry.ts';

function server(lose: 'session' | 'message' | null) {
  const sessions = new Map<string, { id: string; title: string }>();
  const responses = new Map<string, { answer: string; proposalId: string }>();
  let lost = false;
  let modelTurns = 0;
  const client = {
    async createSession(title: string, requestId?: string) {
      assert.ok(requestId);
      if (!sessions.has(requestId)) sessions.set(requestId, { id: `session-${sessions.size + 1}`, title });
      if (lose === 'session' && !lost) {
        lost = true;
        throw new Error('Session committed; response lost');
      }
      return sessions.get(requestId)!;
    },
    async send(sessionId: string, message: string, requestId?: string) {
      assert.ok(requestId);
      const key = `${sessionId}:${requestId}`;
      if (!responses.has(key)) {
        modelTurns += 1;
        responses.set(key, { answer: message, proposalId: `proposal-${modelTurns}` });
      }
      if (lose === 'message' && !lost) {
        lost = true;
        throw new Error('Turn committed; response lost');
      }
      return responses.get(key)!;
    },
  };
  return { client, sessions, responses, turns: () => modelTurns };
}

test('lost session response recovers one session and sends one turn', async () => {
  const s = server('session');
  const ref: { current: ChatAttempt | null } = { current: null };
  const first = chatAttemptFor(ref, null, 'Remind me');
  await assert.rejects(sendChatAttempt(first, s.client));
  const retry = chatAttemptFor(ref, null, 'Remind me');
  assert.equal(retry.requestId, first.requestId);
  await sendChatAttempt(retry, s.client);
  assert.equal(s.sessions.size, 1);
  assert.equal(s.turns(), 1);
});

test('lost successful chat response reuses the committed turn and proposal', async () => {
  const s = server('message');
  const ref: { current: ChatAttempt | null } = { current: null };
  let shown: string | null = null;
  const first = chatAttemptFor(ref, shown, 'Remind me');
  await assert.rejects(sendChatAttempt(first, s.client, (session) => { shown = session.id; }));
  const retry = chatAttemptFor(ref, shown, 'Remind me');
  assert.equal(retry.requestId, first.requestId);
  const response = await sendChatAttempt(retry, s.client);
  assert.equal(response.proposalId, 'proposal-1');
  assert.equal(s.sessions.size, 1);
  assert.equal(s.turns(), 1);
  assert.equal(s.responses.size, 1);
});

test('changed text or conversation is a new request, but an unchanged failed intent is retained', () => {
  const ref: { current: ChatAttempt | null } = { current: null };
  const first = chatAttemptFor(ref, 'a', 'First');
  assert.equal(chatAttemptFor(ref, 'a', 'First').requestId, first.requestId);
  const edited = chatAttemptFor(ref, 'a', 'Edited');
  assert.notEqual(edited.requestId, first.requestId);
  assert.notEqual(chatAttemptFor(ref, 'b', 'Edited').requestId, edited.requestId);
});

test('sending the same words again after a completed response is intentionally a new turn', async () => {
  const s = server(null);
  const ref: { current: ChatAttempt | null } = { current: null };
  const first = chatAttemptFor(ref, 'existing', 'Hello');
  await sendChatAttempt(first, s.client);
  const next = chatAttemptFor(ref, 'existing', 'Hello');
  assert.notEqual(first.requestId, next.requestId);
  await sendChatAttempt(next, s.client);
  assert.equal(s.turns(), 2);
});
