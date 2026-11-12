import assert from 'node:assert/strict';
import test from 'node:test';
import { confirmProposalAttempt } from '../src/proposalRetry.ts';
import type { ProposalAttempt } from '../src/proposalRetry.ts';

function fakeServer(lose: 'create' | 'confirm' | null) {
  const proposals = new Map<string, string>();
  const executed = new Set<string>();
  let lost = false;
  let creates = 0;
  const client = {
    async propose(_kind: string, _payload: Record<string, unknown>, _reason?: string, requestId?: string) {
      creates += 1;
      assert.ok(requestId);
      if (!proposals.has(requestId)) proposals.set(requestId, `proposal-${proposals.size + 1}`);
      const id = proposals.get(requestId)!;
      if (lose === 'create' && !lost) {
        lost = true;
        throw new Error('Create reached server; response lost');
      }
      return { id };
    },
    async confirm(id: string) {
      executed.add(id);
      if (lose === 'confirm' && !lost) {
        lost = true;
        throw new Error('Confirm reached server; response lost');
      }
    },
  };
  return { client, proposals, executed, creates: () => creates };
}

test('lost create response retries the same request and executes once', async () => {
  const server = fakeServer('create');
  const ref: { current: ProposalAttempt | null } = { current: null };
  const payload = { order_id: 'ORD-107', text: 'Follow up', when: 'tomorrow 09:00' };
  await assert.rejects(confirmProposalAttempt(ref, server.client, 'reminder', payload));
  await confirmProposalAttempt(ref, server.client, 'reminder', payload);
  assert.equal(server.proposals.size, 1);
  assert.equal(server.executed.size, 1);
});

test('lost confirm response retries the original proposal without proposing again', async () => {
  const server = fakeServer('confirm');
  const ref: { current: ProposalAttempt | null } = { current: null };
  const payload = { order_id: 'ORD-107', condition: 'completed' };
  await assert.rejects(confirmProposalAttempt(ref, server.client, 'watch', payload));
  await confirmProposalAttempt(ref, server.client, 'watch', payload);
  assert.equal(server.creates(), 1);
  assert.equal(server.proposals.size, 1);
  assert.equal(server.executed.size, 1);
});

test('editing the intent creates a separate request ID', async () => {
  const server = fakeServer(null);
  const ref: { current: ProposalAttempt | null } = { current: null };
  await confirmProposalAttempt(ref, server.client, 'note', { order_id: 'ORD-107', text: 'First note' });
  await confirmProposalAttempt(ref, server.client, 'note', { order_id: 'ORD-107', text: 'Updated note' });
  assert.equal(server.proposals.size, 2);
  assert.equal(server.executed.size, 2);
});
