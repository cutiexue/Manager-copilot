import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import type { OrderHit } from '../types';
import OrderPicker, { orderDetail } from './OrderPicker';

export interface OrderChoice {
  order_id: string;
  customer: string;
  /** One line of context, formatted from fields the backend returned */
  detail?: string;
}

export interface ProposalDraft {
  kind: 'reminder' | 'note';
  /** The order this is about; leave out to search for one in the dialog */
  order?: OrderChoice;
  /** A non-order subject from a briefing finding, e.g. a customer or a production stage */
  subject?: string;
  text: string;
  /** Why it was suggested, e.g. the briefing finding */
  reason?: string;
}

interface Props {
  draft: ProposalDraft;
  /** Called after the backend saved it, with a one-line confirmation to show */
  onDone: (message: string) => void;
  /** Cancel or Esc: nothing is saved */
  onClose: () => void;
}

const textFor = (o: OrderChoice) => `Follow up on ${o.order_id}${o.customer ? ` (${o.customer})` : ''}.`;
const pad = (n: number) => String(n).padStart(2, '0');
const localInput = (d: Date) =>
  `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
function tomorrowNine() {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  d.setHours(9, 0, 0, 0);
  return localInput(d);
}
const readable = (value: string) =>
  new Date(value).toLocaleString([], { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });

// Plan §7.5: a proposal is carried out only when the manager confirms. Confirm here creates the
// proposal and confirms it in one step; Cancel or Esc saves nothing.
export default function ConfirmModal({ draft, onDone, onClose }: Props) {
  const [order, setOrder] = useState<OrderChoice | null>(draft.order ?? null);
  const [subject, setSubject] = useState<string | null>(draft.kind === 'note' ? null : draft.subject ?? null);
  const [text, setText] = useState(draft.text);
  // The text the dialog filled in itself; it follows the chosen order until the manager edits it.
  const [defaultText, setDefaultText] = useState(draft.text);
  const [when, setWhen] = useState(tomorrowNine);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const textRef = useRef<HTMLTextAreaElement>(null);
  const target = order?.order_id ?? subject;
  const isReminder = draft.kind === 'reminder';

  useEffect(() => {
    // With the subject already chosen, start on Cancel so Enter cannot confirm by accident;
    // otherwise the order search takes the focus.
    if (draft.order || draft.subject) cancelRef.current?.focus();
  }, [draft]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && !busy && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, busy]);

  const pick = (o: OrderHit) => {
    const choice = { order_id: o.order_id, customer: o.customer, detail: orderDetail(o) };
    setOrder(choice);
    if (text === defaultText) {
      setText(textFor(choice));
      setDefaultText(textFor(choice));
    }
    window.setTimeout(() => textRef.current?.focus(), 0);
  };

  const confirm = async () => {
    if (!target) return;
    setBusy(true);
    setError(null);
    try {
      const payload: Record<string, unknown> = { text: text.trim() };
      if (order) payload.order_id = order.order_id;
      else payload.subject = subject;
      if (isReminder) payload.when = when;
      const proposal = await api.propose(draft.kind, payload, draft.reason);
      await api.confirm(proposal.id);
      onDone(isReminder ? `Reminder saved for ${readable(when)}` : `Note saved on ${target}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unexpected error.');
      setBusy(false);
    }
  };

  return (
    <div className="scrim center">
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
        <h2 id="confirm-title">New {draft.kind}</h2>

        <div className="field">
          <span className="field-label">About</span>
          {order ? (
            <div className="chosen">
              <span className="chosen-main">
                <strong>{order.order_id}</strong>
                {order.customer && <> · {order.customer}</>}
                {order.detail && <span className="chosen-detail">{order.detail}</span>}
              </span>
              <button className="btn btn-ghost btn-small" onClick={() => setOrder(null)}>
                Change
              </button>
            </div>
          ) : subject ? (
            <div className="chosen">
              <span className="chosen-main">
                <strong>{subject}</strong>
              </span>
              <button className="btn btn-ghost btn-small" onClick={() => setSubject(null)}>
                Pick an order instead
              </button>
            </div>
          ) : (
            <OrderPicker onPick={pick} />
          )}
          {draft.reason && <span className="small muted">Suggested by: {draft.reason}</span>}
        </div>

        <label className="field">
          <span className="field-label">{isReminder ? 'Reminder' : 'Note'} text</span>
          <textarea ref={textRef} value={text} rows={3} onChange={(e) => setText(e.target.value)} />
        </label>

        {isReminder && (
          <label className="field">
            <span className="field-label">When (Singapore time)</span>
            <input className="input" type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} />
          </label>
        )}

        <p className="small" id="confirm-what">
          <strong>What will happen:</strong>{' '}
          {target ? (
            isReminder ? (
              <>
                a reminder about <strong>{target}</strong> is saved and alerts you at {when ? readable(when) : '…'}. Nothing
                is sent to anyone.
              </>
            ) : (
              <>
                a note is saved on <strong>{target}</strong> in this app. The order data is not changed.
              </>
            )
          ) : (
            <>choose the order this {draft.kind} is about.</>
          )}
        </p>
        {error && (
          <p className="picker-error small" role="alert">
            {error}
          </p>
        )}
        <div className="modal-actions">
          <button ref={cancelRef} className="btn" disabled={busy} onClick={onClose}>
            Cancel — do nothing
          </button>
          <button
            className="btn btn-primary"
            disabled={!target || !text.trim() || (isReminder && !when) || busy}
            onClick={() => void confirm()}
          >
            {busy ? 'Saving…' : `✓ Confirm ${draft.kind}`}
          </button>
        </div>
      </div>
    </div>
  );
}
