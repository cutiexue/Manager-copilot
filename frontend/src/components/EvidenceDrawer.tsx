import { useEffect, useRef } from 'react';
import type { EvidenceView } from '../types';

interface Props {
  view: EvidenceView | null;
  rows: Record<string, Record<string, string>>;
  onClose: () => void;
}

export default function EvidenceDrawer({ view, rows, onClose }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const open = view !== null;

  // Focus Close once when the drawer opens. Keyed on `open` only: the parent re-renders every 30 s
  // (follow-up counts) with a new onClose, which must not pull focus or scroll back to the top.
  useEffect(() => {
    if (!open) return;
    closeRef.current?.focus({ preventScroll: true });
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onCloseRef.current();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

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
        {(view.dataVersion || view.dataDate) && (
          <p className="small">Answer data: {view.dataDate ?? 'date not recorded'} · {view.dataVersion ?? 'version not recorded'}</p>
        )}
        {view.warnings?.map((warning, i) => <p key={i} className="small scripted-note">{warning}</p>)}

        {view.calculation.length > 0 && (
          <>
            <h3>{view.calculationTitle ?? 'Calculation (from tool output)'}</h3>
            <dl className="calc">
              {view.calculation.map((c, i) => (
                <div key={`${i}:${c.label}`}>
                  <dt>{c.label}</dt>
                  <dd>{c.value}</dd>
                </div>
              ))}
            </dl>
          </>
        )}

        {!!view.toolResults?.length && (
          <section>
            <h3>Results and assumptions</h3>
            <p className="small muted">Expand a result to inspect the values, dates, warnings and assumptions used for this answer.</p>
            {view.toolResults.map((tool, i) => (
              <details className="tool-result" key={`${i}:${tool.name}`}>
                <summary>{tool.name.replace(/_/g, ' ')}</summary>
                <dl className="calc">
                  {Object.entries(tool.result).filter(([key]) => !['source_rows', 'source'].includes(key)).map(([key, value]) => (
                    <div key={key}>
                      <dt>{key.replace(/_/g, ' ')}</dt>
                      <dd>{typeof value === 'object' && value !== null
                        ? <pre>{JSON.stringify(value, null, 2)}</pre>
                        : String(value ?? 'Not available')}</dd>
                    </div>
                  ))}
                </dl>
              </details>
            ))}
          </section>
        )}

        <h3>Source rows ({view.refs.length})</h3>
        {view.refs.length === 0 && <p className="empty">The tool returned no source rows for this claim.</p>}
        {[...bySource.entries()].map(([source, refs]) => {
          const present = refs.map((r) => sourceRows[r.row_key ?? `${source}#${r.row}`]).filter((raw) => raw !== undefined);
          // Columns from every row, so a row with an extra column (a scripted change) still shows it.
          const cols = [...new Set(present.flatMap((raw) => Object.keys(raw)))];
          const simulated = present.filter((raw) => raw.scripted_change);
          // Chat answers pin each row to a data version; briefing and order rows carry none.
          const versioned = refs.some((r) => r.data_version);
          return (
            <div key={source} className="source-block">
              <p className="small">
                <code>{source}</code>
              </p>
              {simulated.length > 0 && (
                <p className="small scripted-note">
                  Simulated values from a scripted snapshot, not in the course file:{' '}
                  {simulated.map((raw) => `${raw.order_id} (${raw.scripted_change})`).join('; ')}
                </p>
              )}
              <div className="table-scroll">
                <table className="table small">
                  <thead>
                    <tr>
                      <th scope="col">Line</th>
                      {versioned && <th scope="col">Version</th>}
                      {cols.length === 0 && <th scope="col">Availability</th>}
                      {cols.map((c) => (
                        <th scope="col" key={c}>{c}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {refs.map((r) => {
                      const raw = sourceRows[r.row_key ?? `${source}#${r.row}`];
                      return (
                        <tr key={r.row_key ?? `${r.row}:${r.data_version ?? ''}`}>
                          <td>{r.row}</td>
                          {versioned && <td>{r.data_version ?? 'Not recorded'}</td>}
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
