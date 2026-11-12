import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { api } from '../api';
import { scheduleOrderLoad, type LoadOutcome } from '../orderLoad';
import type { EvidenceView, OrderDueFilter, OrderHit, OrderList, OrderStatusFilter, StageCount } from '../types';
import { shortDate } from '../dates';
import { useGlassPointer, useRollingNumber } from '../motion';
import Icon from './Icon';
import LiquidFilter from './LiquidFilter';
import Segmented from './Segmented';

interface Props {
  onEvidence: (v: EvidenceView) => void;
  onAsk: (text: string) => void;
  onRemind: (order: OrderHit) => void;
}

const DUE: { value: OrderDueFilter; label: string }[] = [
  { value: 'all', label: 'Any due date' },
  { value: 'overdue', label: 'Overdue' },
  { value: '7d', label: 'Due in 7 days' },
  { value: '30d', label: 'Due in 30 days' },
];

const STATUS: { value: OrderStatusFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'unfinished', label: 'Unfinished' },
  { value: 'at_risk', label: 'At risk' },
  { value: 'complete', label: 'Complete' },
];

const stageName = (s: string) => s.charAt(0) + s.slice(1).toLowerCase();

function Stat({ label, value, dark }: { label: string; value: number; dark?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  useGlassPointer(ref);
  const shown = useRollingNumber(value);
  return (
    <div ref={ref} className={dark ? 'stat stat-dark' : 'stat glass-card'}>
      <span className="stat-label">{label}</span>
      <span className="stat-value">{Math.round(shown).toLocaleString('en-US')}</span>
    </div>
  );
}

// Unfinished orders at each stage of the line, in production order, among the orders shown. One
// horizontal bar per stage on a shared baseline: its dark part is the orders at risk (the tone of the
// At risk tile above), its light part the other unfinished orders. Both counts come from the backend;
// the bar widths are only drawn from them. Bars glide to new lengths when a filter changes.
function StageChart({ data }: { data: StageCount[] }) {
  const stages = data.filter((d) => d.stage !== 'COMPLETE');
  const top = Math.max(1, ...stages.map((d) => d.orders));
  const [active, setActive] = useState<string | null>(null);
  const empty = stages.every((d) => d.orders === 0);
  return (
    <figure className="stage-chart glass-card" aria-labelledby="stage-chart-title">
      <figcaption>
        <span id="stage-chart-title">Unfinished orders by stage</span>
        <span className="chart-legend">
          <span><i className="chart-key key-risk" aria-hidden /> At risk</span>
          <span><i className="chart-key key-rest" aria-hidden /> Other unfinished</span>
        </span>
      </figcaption>
      {empty ? (
        <p className="empty small">No unfinished orders shown</p>
      ) : (
        <ul className={active ? 'stage-rows has-active' : 'stage-rows'}>
          {stages.map((d) => {
            const label = `${stageName(d.stage)}: ${d.orders} unfinished, ${d.at_risk} at risk`;
            return (
              <li
                key={d.stage}
                className={active === d.stage ? 'stage-row is-active' : 'stage-row'}
                style={{ '--w': `${(d.orders / top) * 100}%` } as CSSProperties}
                tabIndex={0}
                aria-label={label}
                onPointerEnter={() => setActive(d.stage)}
                onPointerLeave={() => setActive(null)}
                onFocus={() => setActive(d.stage)}
                onBlur={() => setActive(null)}
              >
                <span className="stage-name" aria-hidden>{stageName(d.stage)}</span>
                <span className="stage-track" aria-hidden>
                  <span className="stage-bar">
                    {d.at_risk > 0 && <span className="seg seg-risk" style={{ flexGrow: d.at_risk }} />}
                    {d.orders > d.at_risk && <span className="seg seg-rest" style={{ flexGrow: d.orders - d.at_risk }} />}
                  </span>
                  <span className="stage-value">
                    <strong>{d.orders}</strong>
                    {d.at_risk > 0 && <span className="stage-risk"> · {d.at_risk} at risk</span>}
                  </span>
                  {active === d.stage && (
                    <span className="chart-tip" role="tooltip">
                      <span className="chart-tip-title">{stageName(d.stage)}</span>
                      <span className="chart-tip-row"><i className="tip-line key-rest" /> <strong>{d.orders}</strong> unfinished</span>
                      <span className="chart-tip-row"><i className="tip-line key-risk" /> <strong>{d.at_risk}</strong> at risk</span>
                    </span>
                  )}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </figure>
  );
}

// Every order, filtered by due date, status, stage, customer or a search. The backend does the
// filtering and counts the totals, so the figures on this page are never added up in the browser.
export default function OrdersPage({ onEvidence, onAsk, onRemind }: Props) {
  const [due, setDue] = useState<OrderDueFilter>('all');
  const [status, setStatus] = useState<OrderStatusFilter>('all');
  const [stage, setStage] = useState('');
  const [customer, setCustomer] = useState('');
  const [q, setQ] = useState('');
  const [reload, setReload] = useState(0);
  const [result, setResult] = useState<{ key: string; attempt: number; outcome: LoadOutcome<OrderList> } | null>(null);
  const [choices, setChoices] = useState<{ stages: string[]; customers: string[] }>({ stages: [], customers: [] });
  const [actionError, setActionError] = useState<string | null>(null);
  const filterKey = JSON.stringify([status, due, stage, customer, q]);
  // Hide previous rows immediately when the filters change, before the next effect/debounce runs.
  const current = result?.key === filterKey && result.attempt === reload ? result.outcome : null;
  const data = current?.ok ? current.value : null;
  const pending = current === null;
  const loadError = current && !current.ok
    ? (current.error instanceof Error ? current.error.message : 'Unexpected error.') : null;
  const error = loadError ?? actionError;

  useEffect(() => {
    setActionError(null);
    return scheduleOrderLoad(
      () => api.orders({ status, due, stage, customer, q }),
      (outcome) => {
        setResult({ key: filterKey, attempt: reload, outcome });
        if (outcome.ok) setChoices({ stages: outcome.value.stages, customers: outcome.value.customers });
      },
      q ? 200 : 0,
    );
  }, [status, due, stage, customer, q, filterKey, reload]);

  const evidence = async (o: OrderHit) => {
    try {
      const row = await api.evidence(`orders.csv:${o.source_row}`);
      onEvidence({
        title: o.order_id,
        claim: o.risk_reasons.length ? `${o.order_id}: ${o.risk_reasons.join('; ')}` : `${o.order_id}: ${o.status === 'COMPLETE' ? 'complete' : `at ${o.current_stage.toLowerCase()}`}`,
        calculation: [],
        refs: [{ source: row.source, row: row.row, key: o.order_id }],
        rows: { [`${row.source}#${row.row}`]: row.data },
      });
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Unexpected error.');
    }
  };

  const filtered = stage || customer || q;

  return (
    <section className="orders-page" aria-labelledby="orders-title">
      <header className="page-head orders-head">
        <div>
          <h1 id="orders-title">Orders &amp; output</h1>
          <p className="dateline">{data ? `Statuses as of ${data.as_of_date}` : pending ? 'Loading…' : 'Orders unavailable'}</p>
        </div>
        <LiquidFilter label="Due date" options={DUE} value={due} onChange={setDue} />
      </header>

      {error && (
        <p className="alert" role="alert">
          {error}
          <button className="btn btn-small" onClick={() => setReload((n) => n + 1)}>
            <Icon name="refresh" size={14} /> Retry
          </button>
        </p>
      )}

      {data && (
        <>
          <div className="stats">
            <Stat label="Orders shown" value={data.summary.orders} />
            <Stat label="Unfinished" value={data.summary.unfinished} />
            <Stat label="Pieces ordered" value={data.summary.pieces} />
            <Stat label="At risk" value={data.summary.at_risk} dark />
          </div>
          <StageChart data={data.summary.by_stage} />
        </>
      )}

      <div className="glass-panel orders-list">
        <div className="filters">
          <Segmented label="Status" options={STATUS} value={status} onChange={setStatus} />
          <select className="input" value={stage} onChange={(e) => setStage(e.target.value)} aria-label="Stage">
            <option value="">Any stage</option>
            {choices.stages.map((s) => (
              <option key={s} value={s}>{stageName(s)}</option>
            ))}
          </select>
          <select className="input" value={customer} onChange={(e) => setCustomer(e.target.value)} aria-label="Customer">
            <option value="">Any customer</option>
            {choices.customers.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
          <label className="picker-input orders-search">
            <Icon name="search" size={15} />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Order, customer or product" aria-label="Search orders" />
          </label>
          {filtered && (
            <button className="btn btn-ghost btn-small" onClick={() => { setStage(''); setCustomer(''); setQ(''); }}>
              Clear filters
            </button>
          )}
        </div>

        {pending ? (
          <p className="empty" role="status">Loading orders…</p>
        ) : loadError ? (
          <p className="empty">Orders could not be loaded. Retry above.</p>
        ) : data && data.orders.length === 0 ? (
          <p className="empty">No orders match these filters. Clear a filter or pick another due date.</p>
        ) : (
          <div className="rank-card">
            <div className="table-scroll">
              <table className="table orders-table">
                <thead>
                  <tr>
                    <th scope="col">Order</th>
                    <th scope="col">Customer</th>
                    <th scope="col" className="num">Pieces</th>
                    <th scope="col">Due</th>
                    <th scope="col">Stage</th>
                    <th scope="col">Attention</th>
                    <th scope="col"><span className="sr-only">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  {data?.orders.map((o) => (
                    <tr key={o.order_id} className={o.risk_reasons.length ? 'is-risk' : undefined}>
                      <th scope="row">
                        <span className="order-id">{o.order_id}</span>
                        <span className="order-product">{o.product}</span>
                      </th>
                      <td>{o.customer}</td>
                      <td className="num">{o.pieces.toLocaleString('en-US')}</td>
                      <td className="num-date">{shortDate(o.due_date)}</td>
                      <td>{o.status === 'COMPLETE' ? 'Complete' : stageName(o.current_stage)}</td>
                      <td className="order-reasons">
                        {o.risk_reasons.length ? o.risk_reasons.join('; ') : <span className="muted">—</span>}
                      </td>
                      <td className="row-icons">
                        <button className="row-btn" aria-label={`Evidence for ${o.order_id}`} onClick={() => void evidence(o)}>
                          <Icon name="evidence" size={15} />
                          <span className="row-btn-label">Evidence</span>
                        </button>
                        <button className="row-btn" aria-label={`Ask about ${o.order_id}`} onClick={() => onAsk(`What is the latest status of ${o.order_id}?`)}>
                          <Icon name="ask" size={15} />
                          <span className="row-btn-label">Ask</span>
                        </button>
                        {o.status !== 'COMPLETE' && (
                          <button className="row-btn" aria-label={`Remind about ${o.order_id}`} onClick={() => onRemind(o)}>
                            <Icon name="remind" size={15} />
                            <span className="row-btn-label">Remind</span>
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
        {data && <p className="small muted list-source">Source: {data.source}</p>}
      </div>
    </section>
  );
}
