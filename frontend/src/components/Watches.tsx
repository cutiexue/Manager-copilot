import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import type { Alert, SnapshotState, Watch } from '../types';
import { shortDate } from '../dates';
import Icon from './Icon';
import { clock, useAutoRefresh } from '../useAutoRefresh';

interface Props {
  onNewWatch: () => void;
  onChanged: () => void;
  refreshKey: number;
}

const when = (iso: string) =>
  new Date(iso).toLocaleString([], { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });

const STATUS: Record<Watch['status'], string> = {
  ACTIVE: 'Watching', PAUSED: 'Paused', TRIGGERED: 'Triggered', RESOLVED: 'Closed', CANCELLED: 'Cancelled',
};

// Standing watches and the alerts they raise. The course data never changes, so watches are
// checked against scripted data snapshots; "Load next snapshot" moves the whole app to the next day.
export default function Watches({ onNewWatch, onChanged, refreshKey }: Props) {
  const [watches, setWatches] = useState<Watch[] | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [snapshot, setSnapshot] = useState<SnapshotState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [w, a, s] = await Promise.all([api.watches(), api.alerts(), api.snapshot()]);
      setWatches(w);
      setAlerts([...a.filter((x) => !x.read_at), ...a.filter((x) => x.read_at)]);
      setSnapshot(s);
      setError(null);
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unexpected error.');
      return false;
    }
  }, []);

  const updated = useAutoRefresh(load);
  useEffect(() => {
    if (refreshKey) void load();
  }, [load, refreshKey]);

  // Alert policy (README): only a watch or reminder the manager set up interrupts and is counted on the
  // dock. A new briefing is a notice. Findings never alert; they wait for the morning briefing.
  const interrupts = (a: Alert) => a.kind === 'watch' || a.kind === 'reminder';
  const needsAction = alerts.filter(interrupts);
  const notices = alerts.filter((a) => !interrupts(a));

  const run = async (step: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await step();
      await load();
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unexpected error.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel watches" aria-labelledby="watches-title">
      <div className="actions-head">
        <div>
          <h1 id="watches-title">Watches &amp; alerts</h1>
          {updated && <p className="updated small">Updated {clock(updated)} · refreshes every 30 s</p>}
        </div>
        <button className="btn btn-primary" onClick={onNewWatch}>
          <Icon name="plus" size={14} /> New watch
        </button>
      </div>

      {snapshot && (
        <div className="snapshot-bar small">
          <span className="pill" title="The whole app reads this data: the course data, or a scripted snapshot (simulated, not live factory data).">
            Data · {snapshot.current.label}
            {snapshot.current.label.includes(shortDate(snapshot.current.date)) ? '' : ` · ${shortDate(snapshot.current.date)}`}
          </span>
          <button
            className="btn btn-small"
            disabled={!snapshot.next || busy}
            title={snapshot.next ? `Scripted update for demos: ${snapshot.next.label}` : 'This is the last scripted snapshot'}
            onClick={() => void run(api.advanceSnapshot)}
          >
            Load next snapshot
          </button>
          {snapshot.current.version !== snapshot.versions[0]?.version && (
            <button className="btn btn-ghost btn-small" disabled={busy} onClick={() => void run(api.resetSnapshot)}>
              Reset
            </button>
          )}
        </div>
      )}

      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}

      <div className="fu-section">
        <h3>Needs attention · {needsAction.filter((a) => !a.read_at).length} new</h3>
        <p className="fu-rule">Your watches and reminders · counted on the dock</p>
        {needsAction.length === 0 ? (
          <p className="empty small">No alerts.</p>
        ) : (
          <AlertList alerts={needsAction} onRead={(id) => void run(() => api.readAlert(id))} />
        )}
      </div>

      {notices.length > 0 && (
        <div className="fu-section">
          <h3>System notices</h3>
          <p className="fu-rule">New briefings · not counted</p>
          <AlertList alerts={notices} notice onRead={(id) => void run(() => api.readAlert(id))} />
        </div>
      )}

      <div className="fu-section">
        <h3>Watches · {watches?.filter((w) => w.status === 'ACTIVE').length ?? 0} active</h3>
        {!watches ? (
          <p className="muted">Loading…</p>
        ) : watches.length === 0 ? (
          <p className="empty small">None. Ask in chat, e.g. “Tell me if ORD-062 hasn’t moved by Thursday”, or use New watch.</p>
        ) : (
          <ul className="fu-list">
            {watches.map((w) => (
              <li key={w.id}>
                <span className="fu-main">
                  <strong>{w.summary}</strong>
                  {/* last_result is an internal code (met, not_met, resolved, error); show the outcome text instead. */}
                  {w.outcome ? (
                    <span className="muted"> · {w.outcome}</span>
                  ) : w.last_result === 'error' ? (
                    <span className="muted"> · Check failed</span>
                  ) : null}
                </span>
                <span className="fu-side">
                  <span className={`badge badge-${w.status.toLowerCase()}`}>{STATUS[w.status]}</span>
                  {w.status === 'ACTIVE' && (
                    <button className="btn btn-ghost btn-small" disabled={busy} onClick={() => void run(() => api.changeWatch(w.id, 'pause'))}>
                      Pause
                    </button>
                  )}
                  {w.status === 'PAUSED' && (
                    <button className="btn btn-ghost btn-small" disabled={busy} onClick={() => void run(() => api.changeWatch(w.id, 'resume'))}>
                      Resume
                    </button>
                  )}
                  {(w.status === 'ACTIVE' || w.status === 'PAUSED') && (
                    <button className="btn btn-ghost btn-small" disabled={busy} onClick={() => void run(() => api.changeWatch(w.id, 'cancel'))}>
                      Cancel
                    </button>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

function AlertList({ alerts, notice, onRead }: { alerts: Alert[]; notice?: boolean; onRead: (id: string) => void }) {
  return (
    <ul className={`fu-list${notice ? ' fu-notices' : ''}`}>
      {alerts.map((a) => (
        <li key={a.id} className={a.read_at ? 'is-read' : notice ? 'is-notice' : 'is-new'}>
          <span className="fu-when">{when(a.created_at)}</span>
          <span className="fu-main">
            <strong>{a.title}</strong>
            {a.body && <> · {a.body}</>}
          </span>
          <span className="fu-side">
            {!a.read_at && (
              <button className="btn btn-ghost btn-small" onClick={() => onRead(a.id)}>
                Mark read
              </button>
            )}
          </span>
        </li>
      ))}
    </ul>
  );
}
