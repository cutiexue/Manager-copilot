import { useEffect, useRef, useState } from 'react';
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
  /** target: the order ID or subject the action is about */
  onConfirm: (target: string, text: string) => void;
  /** target is null when the dialog is closed before choosing what the action is about */
  onCancel: (target: string | null, text: string) => void;
}

const textFor = (o: OrderChoice) => `Follow up on ${o.order_id}${o.customer ? ` (${o.customer})` : ''}.`;

// Plan §7.5: the agent/UI only proposes; nothing happens until the manager
// explicitly confirms here.
export default function ConfirmModal({ draft, onConfirm, onCancel }: Props) {
  const [order, setOrder] = useState<OrderChoice | null>(draft.order ?? null);
  const [subject, setSubject] = useState<string | null>(draft.subject ?? null);
  const [text, setText] = useState(draft.text);
  // The text the dialog filled in itself; it follows the chosen order until the manager edits it.
  const [defaultText, setDefaultText] = useState(draft.text);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const textRef = useRef<HTMLTextAreaElement>(null);
  const target = order?.order_id ?? subject;

  useEffect(() => {
    // With the subject already chosen, start on Cancel so Enter cannot confirm by accident;
    // otherwise the order search takes the focus.
    if (draft.order || draft.subject) cancelRef.current?.focus();
  }, [draft]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onCancel(target, text);
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onCancel, target, text]);

  const pick = (o: OrderHit) => {
    const choice = { order_id: o.order_id, customer: o.customer, detail: orderDetail(o) };
    setOrder(choice);
    if (text === defaultText) {
      setText(textFor(choice));
      setDefaultText(textFor(choice));
    }
    window.setTimeout(() => textRef.current?.focus(), 0);
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
          <span className="field-label">{draft.kind === 'note' ? 'Note' : 'Reminder'} text</span>
          <textarea ref={textRef} value={text} rows={3} onChange={(e) => setText(e.target.value)} />
        </label>

        <p className="small" id="confirm-what">
          <strong>What will happen:</strong>{' '}
          {target ? (
            <>
              a {draft.kind} about <strong>{target}</strong> is added to the action log with the time you confirm. Nothing
              is sent to anyone.
            </>
          ) : (
            <>choose the order this {draft.kind} is about.</>
          )}
        </p>
        <p className="demo-note small">Demo mode: kept in this browser tab only until the backend action service exists.</p>
        <div className="modal-actions">
          <button ref={cancelRef} className="btn" onClick={() => onCancel(target, text)}>
            Cancel — do nothing
          </button>
          <button
            className="btn btn-primary"
            disabled={!target || !text.trim()}
            onClick={() => target && onConfirm(target, text.trim())}
          >
            ✓ Confirm {draft.kind}
          </button>
        </div>
      </div>
    </div>
  );
}
