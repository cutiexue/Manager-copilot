import { useState } from 'react';
import type { Briefing, EvidenceView } from '../types';
import { evidenceForOrder, evidenceForStage } from '../evidence';

interface Props {
  briefing: Briefing;
  onEvidence: (v: EvidenceView) => void;
  onAsk: (text: string) => void;
}

type Tab = 'yesterday' | 'risk';

export default function DetailPanel({ briefing, onEvidence, onAsk }: Props) {
  const [tab, setTab] = useState<Tab>('yesterday');
  const y = briefing.yesterday;

  return (
    <section className="panel detail" aria-label="Briefing detail">
      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={tab === 'yesterday'} className="tab" onClick={() => setTab('yesterday')}>
          Yesterday's output
        </button>
        <button role="tab" aria-selected={tab === 'risk'} className="tab" onClick={() => setTab('risk')}>
          At-risk orders ({briefing.at_risk.count})
        </button>
      </div>

      {tab === 'yesterday' && (
        <div role="tabpanel">
          <p className="muted small">
            {y.date} · {briefing.comparison_windows.yesterday}
          </p>
          {!y.is_workday ? (
            <p className="empty">{y.message ?? 'Rest day — no output expected.'}</p>
          ) : (
            <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Stage</th>
                  <th scope="col" className="num">Pieces</th>
                  <th scope="col" className="num">Baseline avg</th>
                  <th scope="col" className="num">Change</th>
                  <th scope="col"><span className="sr-only">Evidence</span></th>
                </tr>
              </thead>
              <tbody>
                {y.stages.map((s) => {
                  const c = s.change_percent;
                  return (
                    <tr key={s.stage}>
                      <th scope="row">{s.stage}</th>
                      <td className="num">{s.pieces_completed ?? s.output_status ?? '—'}</td>
                      <td className="num">{s.baseline_average?.toFixed(1) ?? '—'}</td>
                      <td className={`num ${c == null || c === 0 ? '' : c < 0 ? 'down' : 'up'}`}>
                        {c == null ? '—' : `${c < 0 ? '▼ ' : c > 0 ? '▲ +' : ''}${c.toFixed(1)}%`}
                      </td>
                      <td>
                        <button className="btn btn-small" onClick={() => onEvidence(evidenceForStage(y.date, s))}>
                          Evidence
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            </div>
          )}
        </div>
      )}

      {tab === 'risk' && (
        <div role="tabpanel">
          {briefing.at_risk.orders.length === 0 ? (
            <p className="empty">No orders at risk.</p>
          ) : (
            <ul className="risk-list">
              {briefing.at_risk.orders.map((o) => (
                <li key={o.order_id}>
                  <div>
                    <strong>{o.order_id}</strong> <span className="muted">· {o.customer} · {o.current_stage}</span>
                    <div className="small">{o.risk_reasons.join('; ')}</div>
                  </div>
                  <div className="row-actions">
                    <button className="btn btn-small" onClick={() => onEvidence(evidenceForOrder(briefing, o))}>
                      Evidence
                    </button>
                    <button className="btn btn-small" onClick={() => onAsk(`What is the latest status of ${o.order_id}?`)}>
                      Ask
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
