import { useState } from 'react';
import type { Session } from '../types';
import { hrefFor, type Route } from '../route';
import { matchingSessions, sessionGroup as groupOf } from '../sessions';
import Icon from './Icon';

interface Props {
  route: Route;
  sessions: Session[];
  sessionsLoaded: boolean;
  sessionsError: string | null;
}

// Past conversations beside the chat, newest first, with a filter. Shown on the chat pages on wide
// screens; the dock's Conversations page lists them on every screen size.
export default function ChatSidebar({ route, sessions, sessionsLoaded, sessionsError }: Props) {
  const [filter, setFilter] = useState('');
  const recent = matchingSessions(sessions, filter);
  const now = Date.now();
  let last = '';

  return (
    <aside className="chat-sidebar glass-panel" aria-label="Conversations">
      <a className="btn btn-primary new-chat" href={hrefFor({ page: 'home' })}>
        <Icon name="plus" size={15} /> New chat
      </a>
      <label className="picker-input side-filter">
        <Icon name="search" size={14} />
        <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Find a conversation" aria-label="Find a conversation" />
      </label>
      <nav className="side-list">
        {!sessionsLoaded ? (
          <p className="side-note">Loading…</p>
        ) : sessionsError ? (
          <p className="side-note">Conversations appear here when the backend is running.</p>
        ) : recent.length === 0 ? (
          <p className="side-note">{filter ? 'No conversation matches.' : 'No conversations yet. Ask something to start one.'}</p>
        ) : (
          recent.map((s) => {
            const group = groupOf(s, now);
            const head = group !== last ? group : null;
            last = group;
            const active = route.page === 'chat' && route.sessionId === s.id;
            return (
              <div key={s.id}>
                {head && <p className="side-group">{head}</p>}
                <a href={hrefFor({ page: 'chat', sessionId: s.id })} aria-current={active ? 'page' : undefined} title={s.title}>
                  {s.title}
                </a>
              </div>
            );
          })
        )}
      </nav>
    </aside>
  );
}
