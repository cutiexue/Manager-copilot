import { useEffect, useState } from 'react';
import { api } from '../api';
import type { OrderHit, WatchCondition } from '../types';
import type { OrderChoice } from './ConfirmModal';
import OrderPicker, { orderDetail } from './OrderPicker';

interface Props {
  order?: OrderChoice;
  onDone: (message: string) => void;
  onClose: () => void;
}

const CONDITIONS: { value: WatchCondition; label: string }[] = [
  { value: 'not_moved_by', label: 'Has not moved by a date' },
  { value: 'becomes_overdue', label: 'Becomes overdue' },
  { value: 'completed', label: 'Is completed' },
  { value: 'reaches_stage', label: 'Reaches a stage' },
];
const STAGES = ['KNITTING', 'ASSEMBLY', 'WASHING', 'PACKING'];

function nextDay(iso: string) {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
}

// A watch is proposed and confirmed in one step when the manager presses Confirm.
export default function WatchModal({ order: initial, onDone, onClose }: Props) {
  const [order, setOrder] = useState<OrderChoice | null>(initial ?? null);
  const [condition, setCondition] = useState<WatchCondition>('not_moved_by');
  const [deadline, setDeadline] = useState('');
  const [stage, setStage] = useState('PACKING');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Deadlines are dataset dates: default to the day after the watch data's current date.
    api.snapshot().then((s) => setDeadline((d) => d || nextDay(s.current.date)), () => setDeadline((d) => d || '2026-04-02'));
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && !busy && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, busy]);

  const confirm = async () => {
    if (!order) return;
    setBusy(true);
    setError(null);
    try {
      const payload: Record<string, unknown> = { order_id: order.order_id, condition };
      if (condition === 'not_moved_by') payload.deadline = deadline;
      if (condition === 'reaches_stage') payload.stage = stage;
      const proposal = await api.propose('watch', payload);
      await api.confirm(proposal.id);
      onDone(`Watching ${order.order_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unexpected error.');
      setBusy(false);
    }
  };

  return (
    <div className="scrim center">
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="watch-title">
        <h2 id="watch-title">New watch</h2>
        <div className="field">
          <span className="field-label">Order</span>
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
          ) : (
            <OrderPicker
              onPick={(o: OrderHit) => setOrder({ order_id: o.order_id, customer: o.customer, detail: orderDetail(o) })}
            />
          )}
        </div>
        <label className="field">
          <span className="field-label">Alert me when it</span>
          <select className="input" value={condition} onChange={(e) => setCondition(e.target.value as WatchCondition)}>
            {CONDITIONS.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
        </label>
        {condition === 'not_moved_by' && (
          <label className="field">
            <span className="field-label">By (dataset date)</span>
            <input className="input" type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} />
          </label>
        )}
        {condition === 'reaches_stage' && (
          <label className="field">
            <span className="field-label">Stage</span>
            <select className="input" value={stage} onChange={(e) => setStage(e.target.value)}>
              {STAGES.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </label>
        )}
        <p className="small">
          <strong>What will happen:</strong> the watch is checked against the scripted data snapshots and raises one alert
          when the condition holds. You can pause or cancel it on the Watches page.
        </p>
        {error && (
          <p className="picker-error small" role="alert">
            {error}
          </p>
        )}
        <div className="modal-actions">
          <button className="btn" disabled={busy} onClick={onClose}>
            Cancel — do nothing
          </button>
          <button
            className="btn btn-primary"
            disabled={!order || busy || (condition === 'not_moved_by' && !deadline)}
            onClick={() => void confirm()}
          >
            {busy ? 'Saving…' : '✓ Confirm watch'}
          </button>
        </div>
      </div>
    </div>
  );
}
