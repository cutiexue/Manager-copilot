import type { ReactNode } from 'react';
import type { BriefingSource, Session } from '../types';
import { hrefFor, type Page, type Route } from '../route';

interface Props {
  route: Route;
  sessions: Session[];
  sessionsLoaded: boolean;
  sessionsError: string | null;
  asOfDate: string;
  briefingSource: BriefingSource;
  /** Badge numbers, copied from the briefing payload and the action log */
  counts: { decisions: number; atRisk: number; actions: number };
  /** Called on every link click, e.g. to close the menu on small screens */
  onPick: () => void;
}

const Icon = ({ d }: { d: string }) => (
  <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden fill="none" stroke="currentColor" strokeWidth="2"
    strokeLinecap="round" strokeLinejoin="round">
    <path d={d} />
  </svg>
);

const ICONS = {
  plus: 'M12 5v14M5 12h14',
  briefing: 'M7 3h10a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2zM9 8h6M9 12h6M9 16h4',
  orders: 'M3 20h18M6 20V11M12 20V5M18 20v-7',
  actions: 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0zM8 12l3 3 5-6',
};

const SOURCE_LABEL: Record<BriefingSource, string> = {
  live: 'Briefing: live',
  checking: 'Briefing: checking…',
  snapshot: 'Briefing: snapshot',
};

export default function Sidebar({ route, sessions, sessionsLoaded, sessionsError, asOfDate, briefingSource, counts, onPick }: Props) {
  const nav: { page: Page; label: string; icon: string; count?: number }[] = [
    { page: 'briefing', label: 'Briefing', icon: ICONS.briefing, count: counts.decisions },
    { page: 'orders', label: 'Orders & output', icon: ICONS.orders, count: counts.atRisk },
    { page: 'actions', label: 'Actions', icon: ICONS.actions, count: counts.actions || undefined },
  ];
  // Conversations that never got a message are not worth listing.
  const recent = sessions.filter((s) => s.has_messages !== false);

  let recentBody: ReactNode;
  if (!sessionsLoaded) recentBody = <p className="side-note">Loading…</p>;
  else if (sessionsError) recentBody = <p className="side-note">Conversations appear here when the backend is running.</p>;
  else if (recent.length === 0) recentBody = <p className="side-note">No conversations yet.</p>;
  else
    recentBody = recent.map((s) => {
      const active = route.page === 'chat' && route.sessionId === s.id;
      return (
        <a key={s.id} href={hrefFor({ page: 'chat', sessionId: s.id })} aria-current={active ? 'page' : undefined}
          title={s.title} onClick={onPick}>
          <span>{s.title}</span>
        </a>
      );
    });

  return (
    <nav className="sidebar" aria-label="Main">
      <div className="brand">
        <span className="logo" aria-hidden>◆</span>
        <div>
          <h1>Manager Co-Pilot</h1>
          <p>SweaterCo · General Manager</p>
        </div>
      </div>

      <a className="btn btn-primary new-chat" href={hrefFor({ page: 'home' })}
        aria-current={route.page === 'home' ? 'page' : undefined} onClick={onPick}>
        <Icon d={ICONS.plus} /> New chat
      </a>

      <div className="nav">
        {nav.map((item) => (
          <a key={item.page} href={hrefFor({ page: item.page })} aria-current={route.page === item.page ? 'page' : undefined}
            onClick={onPick}>
            <Icon d={item.icon} />
            {item.label}
            {item.count !== undefined && <span className="count">{item.count}</span>}
          </a>
        ))}
      </div>

      <div className="recent">
        <p className="nav-label">Recent</p>
        {recentBody}
      </div>

      <div className="sidebar-foot">
        <span className="pill" title="Business analysis uses the dataset clock, not today's date.">Data as of {asOfDate}</span>
        <span className={briefingSource === 'live' ? 'pill' : 'pill pill-warn'}>{SOURCE_LABEL[briefingSource]}</span>
      </div>
    </nav>
  );
}
