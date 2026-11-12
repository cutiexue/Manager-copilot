import type { ProposalKind } from './types';

export interface ProposalAttempt {
  signature: string;
  requestId: string;
  proposalId?: string;
}

interface ProposalClient {
  propose: (kind: ProposalKind, payload: Record<string, unknown>, reason?: string, requestId?: string) => Promise<{ id: string }>;
  confirm: (id: string) => Promise<unknown>;
}

/** Keep the identity of a user intent across lost create/confirm responses. Editing makes a new intent. */
export async function confirmProposalAttempt(
  ref: { current: ProposalAttempt | null }, client: ProposalClient, kind: ProposalKind,
  payload: Record<string, unknown>, reason?: string,
) {
  const signature = JSON.stringify([kind, payload, reason ?? null]);
  if (ref.current?.signature !== signature) {
    ref.current = { signature, requestId: crypto.randomUUID() };
  }
  const attempt = ref.current;
  if (!attempt.proposalId) {
    const proposal = await client.propose(kind, payload, reason, attempt.requestId);
    attempt.proposalId = proposal.id;
  }
  return client.confirm(attempt.proposalId);
}
