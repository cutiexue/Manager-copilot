import { useState } from 'react';
import type { Session } from '../types';
import { hrefFor } from '../route';
import { matchingSessions, sessionGroup, sessionWhen } from '../sessions';
import Icon from './Icon';

interface Props {
  sessions: Session[];
  sessionsLoaded: boolean;
  sessionsError: string | null;
  onRetry: () => void;
}

// Every past conversation, newest first, grouped by day, with a filter. The dock's Conversations item
// opens this page on every screen size; opening a row continues that conversation.
export default function Conversations({ sessions, sessionsLoaded, sessionsError, onRetry }: Props) {
  const [filter, setFilter] = useState('');
  const shown = matchingSessions(sessions, filter);
  const total = matchingSessions(sessions, '').length;
  const now = Date.now();
  let last = '';

  return (
    <section className="conversations-page" aria-labelledby="chats-title">
      <header className="page-head">
        <div>
          <h1 id="chats-title">Conversations</h1>
          {total > 0 && <p className="dateline">{total} {total === 1 ? 'conversation' : 'conversations'}</p>}
        </div>
        <a className="btn btn-primary" href={hrefFor({ page: 'home' })}>
          <Icon name="plus" size={15} /> New chat
        </a>
      </header>

      <div className="glass-panel conversations-list">
        {total > 0 && (
          <label className="picker-input">
            <Icon name="search" size={15} />
            <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Find a conversation"
              aria-label="Find a conversation" />
          </label>
        )}
        {!sessionsLoaded ? (
          <p className="empty">Loading…</p>
        ) : sessionsError ? (
          <p className="empty">
            Backend offline.{' '}
            <button className="btn btn-small" onClick={onRetry}>
              <Icon name="refresh" size={14} /> Retry
            </button>
          </p>
        ) : total === 0 ? (
          <p className="empty">No conversations yet.</p>
        ) : shown.length === 0 ? (
          <p className="empty">No conversation matches.</p>
        ) : (
          <ul className="conv-rows">
            {shown.map((s) => {
              const group = sessionGroup(s, now);
              const head = group !== last ? group : null;
              last = group;
              return (
                <li key={s.id}>
                  {head && <p className="side-group">{head}</p>}
                  <a className="conv-row" href={hrefFor({ page: 'chat', sessionId: s.id })}>
                    <Icon name="chats" size={16} />
                    <span className="conv-title">{s.title}</span>
                    <span className="conv-when">{sessionWhen(s, now)}</span>
                  </a>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}
