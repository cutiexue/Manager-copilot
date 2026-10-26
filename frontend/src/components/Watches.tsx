import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import type { Alert, SnapshotState, Watch } from '../types';
import { shortDate } from '../dates';
import Icon from './Icon';

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
// checked against scripted data snapshots; "Load next snapshot" steps through them for demos.
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
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unexpected error.');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

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
        <h2 id="watches-title">Watches &amp; alerts</h2>
        <button className="btn btn-primary" onClick={onNewWatch}>
          <Icon name="plus" size={14} /> New watch
        </button>
      </div>

      {snapshot && (
        <div className="snapshot-bar small">
          <span className="pill" title="Watches are checked against scripted data snapshots, not live factory data.">
            Watch data · {snapshot.current.label}
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
        <h3>Alerts · {alerts.filter((a) => !a.read_at).length} new</h3>
        {alerts.length === 0 ? (
          <p className="empty small">None.</p>
        ) : (
          <ul className="fu-list">
            {alerts.map((a) => (
              <li key={a.id} className={a.read_at ? 'is-read' : 'is-new'}>
                <span className="fu-when">{when(a.created_at)}</span>
                <span className="fu-main">
                  <strong>{a.title}</strong>
                  {a.body && <> · {a.body}</>}
                </span>
                <span className="fu-side">
                  {!a.read_at && (
                    <button className="btn btn-ghost btn-small" onClick={() => void run(() => api.readAlert(a.id))}>
                      Mark read
                    </button>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

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
                  {(w.outcome || w.last_result) && <span className="muted"> · {w.outcome ?? w.last_result}</span>}
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
