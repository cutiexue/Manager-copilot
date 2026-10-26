import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import type { AuditEvent, ChaseDraft, OrderNote, Proposal, Reminder } from '../types';
import Icon from './Icon';
import ProposalCard from './ProposalCard';

interface Props {
  onNewReminder: () => void;
  /** Something was confirmed, cancelled or dismissed here */
  onChanged: () => void;
  /** Bumped by the app when something was saved elsewhere, to reload this page */
  refreshKey: number;
}

interface Data {
  pending: Proposal[];
  reminders: Reminder[];
  notes: OrderNote[];
  drafts: ChaseDraft[];
  audit: AuditEvent[];
}

const when = (iso: string) =>
  new Date(iso).toLocaleString([], { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });

const ACTOR: Record<AuditEvent['actor'], string> = { agent: 'Co-Pilot', user: 'You', system: 'System', scheduler: 'Scheduler' };
const EVENT: Record<string, string> = {
  proposal_created: 'Proposed', confirmed: 'Confirmed', executed: 'Saved', cancelled: 'Cancelled',
  proposal_expired: 'Expired', failed: 'Failed', reminder_due: 'Reminder due', reminder_dismissed: 'Reminder dismissed',
  watch_triggered: 'Watch triggered', watch_resolved: 'Watch closed', watch_paused: 'Watch paused',
  watch_resumed: 'Watch resumed', watch_cancelled: 'Watch cancelled', alert_raised: 'Alert',
  data_snapshot_loaded: 'Data snapshot loaded', briefing_generated: 'Briefing generated', job_failed: 'Job failed',
};

function detail(e: AuditEvent): string {
  const d = e.detail ?? {};
  const text = d.summary ?? d.title ?? d.label ?? d.error ?? d.detail ?? e.target_kind?.replace('_', ' ') ?? '';
  return typeof text === 'string' ? text : '';
}

// Everything the manager has asked Co-Pilot to follow up, all saved by the backend.
export default function FollowUps({ onNewReminder, onChanged, refreshKey }: Props) {
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [pending, reminders, notes, drafts, audit] = await Promise.all([
        api.proposals('PROPOSED'), api.reminders(), api.notes(), api.drafts(), api.audit(40),
      ]);
      setData({ pending, reminders: reminders.filter((r) => r.status !== 'DISMISSED'), notes, drafts, audit });
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unexpected error.');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  const changed = () => {
    void load();
    onChanged();
  };

  const dismiss = async (id: string) => {
    try {
      await api.dismissReminder(id);
      changed();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unexpected error.');
    }
  };

  return (
    <section className="panel followups" aria-labelledby="actions-title">
      <div className="actions-head">
        <h2 id="actions-title">Actions</h2>
        <button className="btn btn-primary" onClick={onNewReminder}>
          <Icon name="plus" size={14} /> New reminder
        </button>
      </div>
      {error && (
        <p className="alert" role="alert">
          {error}
          <button className="btn btn-small" onClick={() => void load()}>
            <Icon name="refresh" size={14} /> Retry
          </button>
        </p>
      )}
      {!data && !error && <p className="muted">Loading…</p>}

      {data && (
        <>
          {data.pending.length > 0 && (
            <div className="fu-section">
              <h3>Waiting for you · {data.pending.length}</h3>
              {data.pending.map((p) => (
                <ProposalCard key={p.id} proposal={p} onChanged={changed} />
              ))}
            </div>
          )}

          <div className="fu-section">
            <h3>Reminders · {data.reminders.length}</h3>
            {data.reminders.length === 0 ? (
              <p className="empty small">None.</p>
            ) : (
              <ul className="fu-list">
                {data.reminders.map((r) => (
                  <li key={r.id} className={r.status === 'DUE' ? 'is-due' : undefined}>
                    <span className="fu-when">{when(r.remind_at)}</span>
                    <span className="fu-main">
                      <strong>{r.order_id ?? r.subject ?? 'General'}</strong> · {r.text}
                    </span>
                    <span className="fu-side">
                      {r.status === 'DUE' && <span className="badge badge-due">Due</span>}
                      <button className="btn btn-ghost btn-small" onClick={() => void dismiss(r.id)}>
                        Dismiss
                      </button>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="fu-section">
            <h3>Notes · {data.notes.length}</h3>
            {data.notes.length === 0 ? (
              <p className="empty small">None.</p>
            ) : (
              <ul className="fu-list">
                {data.notes.map((n) => (
                  <li key={n.id}>
                    <span className="fu-when">{when(n.created_at)}</span>
                    <span className="fu-main">
                      <strong>{n.order_id}</strong> · {n.text}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="fu-section">
            <h3>Chase-up drafts · {data.drafts.length}</h3>
            {data.drafts.length === 0 ? (
              <p className="empty small">None.</p>
            ) : (
              <ul className="fu-list">
                {data.drafts.map((d) => (
                  <li key={d.id} className="fu-draft">
                    <span className="fu-main">
                      <strong>{d.customer}</strong> · {d.order_id} · <span className="muted">not sent</span>
                      <blockquote className="proposal-text">{d.text}</blockquote>
                    </span>
                    <span className="fu-side">
                      <button className="btn btn-ghost btn-small" onClick={() => void navigator.clipboard?.writeText(d.text)}>
                        Copy
                      </button>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="fu-section">
            <h3>History</h3>
            {data.audit.length === 0 ? (
              <p className="empty small">Nothing yet.</p>
            ) : (
              <ul className="fu-list fu-audit small">
                {data.audit.map((e) => (
                  <li key={e.id}>
                    <span className="fu-when">{when(e.at)}</span>
                    <span className="fu-main">
                      <strong>{EVENT[e.event] ?? e.event}</strong> · {ACTOR[e.actor] ?? e.actor}
                      {detail(e) && <span className="muted"> · {detail(e)}</span>}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </section>
  );
}
