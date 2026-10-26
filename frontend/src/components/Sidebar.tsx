import type { ReactNode } from 'react';
import type { BriefingSource, Session } from '../types';
import { hrefFor, type Page, type Route } from '../route';
import Icon, { type IconName } from './Icon';
import ThemeSwitch from './ThemeSwitch';

interface Props {
  route: Route;
  sessions: Session[];
  sessionsLoaded: boolean;
  sessionsError: string | null;
  asOfDate: string;
  briefingSource: BriefingSource;
  /** Where the briefing came from (generator, time, backend commit), shown on hover */
  briefingDetail: string;
  /** Badge numbers, copied from the briefing payload and the action log */
  counts: { decisions: number; atRisk: number; actions: number; alerts: number };
  /** Called on every link click, e.g. to close the menu on small screens */
  onPick: () => void;
}

const SOURCE_LABEL: Record<BriefingSource, string> = {
  live: 'Briefing: live',
  checking: 'Briefing: checking…',
  snapshot: 'Briefing: snapshot',
};

export default function Sidebar({
  route, sessions, sessionsLoaded, sessionsError, asOfDate, briefingSource, briefingDetail, counts, onPick,
}: Props) {
  const nav: { page: Page; label: string; icon: IconName; count?: number }[] = [
    { page: 'briefing', label: 'Briefing', icon: 'briefing', count: counts.decisions },
    { page: 'orders', label: 'Orders & output', icon: 'orders', count: counts.atRisk },
    { page: 'actions', label: 'Actions', icon: 'actions', count: counts.actions || undefined },
    { page: 'watches', label: 'Watches & alerts', icon: 'watch', count: counts.alerts || undefined },
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

      <a className="new-chat" href={hrefFor({ page: 'home' })} aria-current={route.page === 'home' ? 'page' : undefined}
        onClick={onPick}>
        <span className="new-chat-icon"><Icon name="plus" size={14} /></span>
        New chat
      </a>

      <div className="nav">
        {nav.map((item) => (
          <a key={item.page} href={hrefFor({ page: item.page })} aria-current={route.page === item.page ? 'page' : undefined}
            onClick={onPick}>
            <Icon name={item.icon} />
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
        <span className={briefingSource === 'live' ? 'pill' : 'pill pill-warn'} title={briefingDetail}>
          {SOURCE_LABEL[briefingSource]}
        </span>
        <div className="theme-row">
          <ThemeSwitch />
        </div>
      </div>
    </nav>
  );
}
