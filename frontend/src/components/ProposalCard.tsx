import { useState } from 'react';
import { api } from '../api';
import type { Proposal } from '../types';

export const KIND_LABEL: Record<Proposal['kind'], string> = {
  reminder: 'Reminder',
  note: 'Note',
  chase_message: 'Chase-up draft',
  watch: 'Watch',
};

const DONE: Record<Proposal['kind'], string> = {
  reminder: '✓ Reminder saved',
  note: '✓ Note saved',
  chase_message: '✓ Saved as a draft · not sent',
  watch: '✓ Watching',
};

function outcome(p: Proposal): string {
  if (p.status === 'EXECUTED') return DONE[p.kind];
  if (p.status === 'CANCELLED') return 'Cancelled · nothing saved';
  if (p.status === 'EXPIRED') return 'Expired · nothing saved';
  return `Failed · ${p.error ?? 'nothing saved'}`;
}

interface Props {
  proposal: Proposal;
  onChanged: (proposal: Proposal) => void;
}

// A proposed follow-up waiting for the manager. Confirm is the only way it is carried out;
// the card then shows what happened.
export default function ProposalCard({ proposal, onChanged }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const text = typeof proposal.payload.text === 'string' ? proposal.payload.text : null;

  const decide = async (confirm: boolean) => {
    setBusy(true);
    setError(null);
    try {
      onChanged(confirm ? (await api.confirm(proposal.id)).proposal : await api.cancel(proposal.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unexpected error.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={`proposal proposal-${proposal.status.toLowerCase()}`}>
      <span className="proposal-kind">{KIND_LABEL[proposal.kind]}</span>
      <p className="proposal-summary">{proposal.summary.replace(/^Reminder · /, '')}</p>
      {proposal.kind === 'chase_message' && text && <blockquote className="proposal-text">{text}</blockquote>}
      {proposal.status === 'PROPOSED' ? (
        <div className="proposal-actions">
          <button className="btn btn-small" disabled={busy} onClick={() => void decide(false)}>
            Cancel
          </button>
          <button className="btn btn-primary btn-small" disabled={busy} onClick={() => void decide(true)}>
            ✓ Confirm
          </button>
        </div>
      ) : (
        <p className="proposal-outcome small">{outcome(proposal)}</p>
      )}
      {error && <p className="picker-error small">{error}</p>}
    </div>
  );
}
