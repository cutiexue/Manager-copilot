import { type KeyboardEvent, useEffect, useRef, useState } from 'react';
import { api } from '../api';
import type { OrderHit, OrderSearchResult } from '../types';
import Icon from './Icon';

interface Props {
  onPick: (order: OrderHit) => void;
}

const LIMIT = 6;

/** One line of context for an order, formatted from fields the backend returned. */
export function orderDetail(o: OrderHit): string {
  return [o.product, `${o.pieces} pcs`, o.status === 'COMPLETE' ? 'complete' : o.current_stage, `due ${o.due_date}`].join(' · ');
}

// Search runs on the backend and returns only the first few matches, so this stays quick however
// many orders exist. Up/Down move through the results, Enter picks the highlighted one.
export default function OrderPicker({ onPick }: Props) {
  const [query, setQuery] = useState('');
  const [result, setResult] = useState<OrderSearchResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState(0);
  const latest = useRef(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    const request = ++latest.current;
    const timer = window.setTimeout(
      () => {
        api.searchOrders(query.trim(), LIMIT).then(
          (r) => {
            if (request !== latest.current) return;
            setResult(r);
            setError(null);
            setActive(0);
          },
          (e) => {
            if (request !== latest.current) return;
            setResult(null);
            setError(e instanceof Error ? e.message : 'Search failed.');
          },
        );
      },
      query ? 200 : 0,
    );
    return () => window.clearTimeout(timer);
  }, [query]);

  const orders = result?.orders ?? [];
  const typed = query.trim();

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown' && orders.length) {
      e.preventDefault();
      setActive((i) => (i + 1) % orders.length);
    } else if (e.key === 'ArrowUp' && orders.length) {
      e.preventDefault();
      setActive((i) => (i - 1 + orders.length) % orders.length);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (orders[active]) onPick(orders[active]);
    }
  };

  // The list keeps the previous results while a new search runs; the summary only describes
  // results that belong to what is typed now.
  let summary: string;
  if (!result || result.query !== typed) summary = 'Searching…';
  else if (!typed) summary = `Unfinished orders, at-risk first · ${result.count} of ${result.total} shown`;
  else if (result.total === 0) summary = `No order matches “${typed}”.`;
  else
    summary = `${result.total} matching ${result.total === 1 ? 'order' : 'orders'}${
      result.total > result.count ? ` · first ${result.count} shown, type more to narrow down` : ''
    }`;

  return (
    <div className="picker">
      <div className="picker-input">
        <Icon name="search" />
        <input
          ref={inputRef}
          type="search"
          role="combobox"
          aria-label="Search orders"
          aria-expanded={orders.length > 0}
          aria-controls="order-results"
          aria-activedescendant={orders[active] ? `order-option-${orders[active].order_id}` : undefined}
          placeholder="Order ID, customer or product"
          value={query}
          autoComplete="off"
          spellCheck={false}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={onKeyDown}
        />
      </div>
      {error ? (
        <p className="picker-error small" role="alert">
          Order search needs the backend. {error}
        </p>
      ) : (
        <p className="picker-meta small" aria-live="polite">
          {summary}
        </p>
      )}
      {orders.length > 0 && (
        <ul id="order-results" role="listbox" aria-label="Orders" className="picker-list">
          {orders.map((o, i) => (
            <li
              key={o.order_id}
              id={`order-option-${o.order_id}`}
              role="option"
              aria-selected={i === active}
              className={i === active ? 'is-active' : undefined}
              onMouseEnter={() => setActive(i)}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => onPick(o)}
            >
              <span className="opt-id">{o.order_id}</span>
              <span className="opt-main">
                <span className="opt-customer">{o.customer}</span>
                <span className="opt-detail">{orderDetail(o)}</span>
              </span>
              {o.risk_reasons.length > 0 && <span className="opt-risk">{o.risk_reasons[0]}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
