import { useEffect, useRef } from 'react';
import type { EvidenceView } from '../types';

interface Props {
  view: EvidenceView | null;
  rows: Record<string, Record<string, string>>;
  onClose: () => void;
}

export default function EvidenceDrawer({ view, rows, onClose }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!view) return;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [view, onClose]);

  if (!view) return null;
  // A chat answer brings its own rows; briefing evidence uses the rows that came with the briefing.
  const sourceRows = view.rows ?? rows;

  // Group cited rows by source file so each file renders as one table.
  const bySource = new Map<string, typeof view.refs>();
  for (const r of view.refs) bySource.set(r.source, [...(bySource.get(r.source) ?? []), r]);

  return (
    <div className="scrim" onClick={onClose}>
      <aside
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="evidence-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="drawer-head">
          <h2 id="evidence-title">Evidence · {view.title}</h2>
          <button ref={closeRef} className="btn" onClick={onClose} aria-label="Close evidence">
            Close ✕
          </button>
        </div>

        <h3>Claim</h3>
        <p>{view.claim}</p>

        {view.calculation.length > 0 && (
          <>
            <h3>Calculation (from tool output)</h3>
            <dl className="calc">
              {view.calculation.map((c) => (
                <div key={c.label}>
                  <dt>{c.label}</dt>
                  <dd>{c.value}</dd>
                </div>
              ))}
            </dl>
          </>
        )}

        <h3>Source rows ({view.refs.length})</h3>
        {view.refs.length === 0 && <p className="empty">The tool returned no source rows for this claim.</p>}
        {[...bySource.entries()].map(([source, refs]) => {
          const first = sourceRows[`${source}#${refs[0].row}`];
          const cols = first ? Object.keys(first) : [];
          return (
            <div key={source} className="source-block">
              <p className="small">
                <code>{source}</code>
              </p>
              <div className="table-scroll">
                <table className="table small">
                  <thead>
                    <tr>
                      <th scope="col">Line</th>
                      {cols.map((c) => (
                        <th scope="col" key={c}>{c}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {refs.map((r) => {
                      const raw = sourceRows[`${source}#${r.row}`];
                      return (
                        <tr key={r.row}>
                          <td>{r.row}</td>
                          {raw ? cols.map((c) => <td key={c}>{raw[c]}</td>) : <td colSpan={cols.length || 1}>{r.key} (row not in snapshot)</td>}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          );
        })}
      </aside>
    </div>
  );
}
