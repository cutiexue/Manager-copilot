import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react';
import { api } from '../api';
import type { EvidenceView, OrderDueFilter, OrderHit, OrderList, OrderStatusFilter } from '../types';
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

// Unfinished orders by the stage they are at, among the orders shown. Bars glide to their new height
// when a filter changes; the pale track behind each bar is the tallest bar's height.
function StageChart({ data }: { data: { stage: string; orders: number }[] }) {
  const stages = data.filter((d) => d.stage !== 'COMPLETE');
  const top = Math.max(1, ...stages.map((d) => d.orders));
  return (
    <figure className="stage-chart glass-card" aria-label="Unfinished orders by stage">
      <figcaption>
        Unfinished orders by stage
        <span>Complete orders are not drawn</span>
      </figcaption>
      <div className="bars" style={{ '--bars': stages.length } as CSSProperties}>
        {stages.map((d) => (
          <div key={d.stage} className="bar-col">
            <span className="bar-value">{d.orders}</span>
            <span className="bar-track">
              <span className="bar-fill" style={{ transform: `translateY(${(1 - d.orders / top) * 100}%)` }} />
            </span>
            <span className="bar-label">{stageName(d.stage)}</span>
          </div>
        ))}
      </div>
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
  const [data, setData] = useState<OrderList | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await api.orders({ status, due, stage, customer, q }));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unexpected error.');
    }
  }, [status, due, stage, customer, q]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), q ? 200 : 0);
    return () => window.clearTimeout(timer);
  }, [load, q]);

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
      setError(e instanceof Error ? e.message : 'Unexpected error.');
    }
  };

  const filtered = stage || customer || q;

  return (
    <section className="orders-page" aria-labelledby="orders-title">
      <header className="page-head orders-head">
        <div>
          <h1 id="orders-title">Orders &amp; output</h1>
          <p className="dateline">{data ? `Statuses as of ${data.as_of_date}` : 'Loading…'}</p>
        </div>
        <LiquidFilter label="Due date" options={DUE} value={due} onChange={setDue} />
      </header>

      {error && (
        <p className="alert" role="alert">
          {error}
          <button className="btn btn-small" onClick={() => void load()}>
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
            {data?.stages.map((s) => (
              <option key={s} value={s}>{stageName(s)}</option>
            ))}
          </select>
          <select className="input" value={customer} onChange={(e) => setCustomer(e.target.value)} aria-label="Customer">
            <option value="">Any customer</option>
            {data?.customers.map((c) => (
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

        {data && data.orders.length === 0 ? (
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
