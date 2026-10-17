import { useEffect, useRef, useState } from 'react';

export interface ProposalDraft {
  kind: 'reminder' | 'note';
  target: string;
  text: string;
  reason: string;
  proposalId?: string;
}

interface Props {
  draft: ProposalDraft;
  onConfirm: (text: string) => void;
  onCancel: () => void;
}

// Plan §7.5: the agent/UI only proposes; nothing happens until the manager
// explicitly confirms here.
export default function ConfirmModal({ draft, onConfirm, onCancel }: Props) {
  const [text, setText] = useState(draft.text);
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    cancelRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onCancel();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onCancel]);

  return (
    <div className="scrim center">
      <div className="modal" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title" aria-describedby="confirm-what">
        <h2 id="confirm-title">Confirm: create {draft.kind}</h2>
        <div id="confirm-what">
          <p>
            <strong>What will happen:</strong> a {draft.kind} for <strong>{draft.target}</strong> is added to the
            action log with the time it was confirmed.
          </p>
          <p className="small muted">Why: {draft.reason}</p>
        </div>
        <label className="field">
          <span className="small">Reminder text</span>
          <textarea value={text} rows={4} onChange={(e) => setText(e.target.value)} />
        </label>
        <p className="demo-note small">
          Demo mode: the backend has no action endpoint yet, so this is kept in this browser tab only and is not
          saved or sent anywhere.
        </p>
        <div className="modal-actions">
          <button ref={cancelRef} className="btn" onClick={onCancel}>
            Cancel — do nothing
          </button>
          <button className="btn btn-confirm" onClick={() => onConfirm(text.trim() || draft.text)}>
            ✓ Confirm and create
          </button>
        </div>
      </div>
    </div>
  );
}
