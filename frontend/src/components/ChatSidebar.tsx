import { useState } from 'react';
import type { Session } from '../types';
import { hrefFor, type Route } from '../route';
import Icon from './Icon';

interface Props {
  route: Route;
  sessions: Session[];
  sessionsLoaded: boolean;
  sessionsError: string | null;
}

const DAY = 86_400_000;

/** Today, Previous 7 days or Older, by when the conversation last changed (real time). */
function groupOf(s: Session, now: number): string {
  const at = Date.parse(s.updated_at ?? s.created_at ?? '');
  if (Number.isNaN(at)) return 'Older';
  if (new Date(at).toDateString() === new Date(now).toDateString()) return 'Today';
  return now - at < 7 * DAY ? 'Previous 7 days' : 'Older';
}

// Past conversations beside the chat, newest first, with a filter. Shown on the chat pages on wide
// screens; on narrow ones the dock's Conversations button lists them instead.
export default function ChatSidebar({ route, sessions, sessionsLoaded, sessionsError }: Props) {
  const [filter, setFilter] = useState('');
  const words = filter.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const recent = sessions
    .filter((s) => s.has_messages !== false)
    .filter((s) => words.every((w) => s.title.toLowerCase().includes(w)));
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
