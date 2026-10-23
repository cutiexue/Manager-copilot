import type { ActionProposal } from '../types';
import Icon from './Icon';

const STATE_LABEL = { PROPOSED: '… Proposed', CONFIRMED: '✓ Confirmed', CANCELLED: '✕ Cancelled' } as const;

const time = (iso?: string) => (iso ? new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '');

export default function ActionLog({ actions, onNewReminder }: { actions: ActionProposal[]; onNewReminder: () => void }) {
  return (
    <section className="panel actions" aria-labelledby="actions-title">
      <div className="actions-head">
        <h2 id="actions-title">
          Actions &amp; audit <span className="pill pill-warn small">demo · not saved</span>
        </h2>
        <button className="btn btn-primary" onClick={onNewReminder}>
          <Icon name="plus" size={14} /> New reminder
        </button>
      </div>
      {actions.length === 0 ? (
        <p className="empty small">
          No actions yet. Use “New reminder” to pick any order, or “Remind…” on a briefing item or an at-risk order. You
          will be asked to confirm first.
        </p>
      ) : (
        <table className="table small">
          <thead>
            <tr>
              <th scope="col">ID</th>
              <th scope="col">State</th>
              <th scope="col">Type</th>
              <th scope="col">Target</th>
              <th scope="col">Text</th>
              <th scope="col">Proposed</th>
              <th scope="col">Decided</th>
            </tr>
          </thead>
          <tbody>
            {actions.map((a) => (
              <tr key={a.id}>
                <td><code>{a.id}</code></td>
                <td className={`state state-${a.state.toLowerCase()}`}>{STATE_LABEL[a.state]}</td>
                <td>{a.kind}</td>
                <td>{a.target}</td>
                <td className="clip">{a.text}</td>
                <td>{time(a.created_at)}</td>
                <td>{time(a.decided_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
