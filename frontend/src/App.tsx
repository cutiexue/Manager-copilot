import { useCallback, useEffect, useState } from 'react';
import fixtureJson from './fixtures/briefing.json';
import { api } from './api';
import { useRoute, type Page } from './route';
import type { BriefingFixture, BriefingSource, EvidenceView, FollowUpCounts, Session } from './types';
import Sidebar from './components/Sidebar';
import TodayDigest, { suggestionsFor } from './components/TodayDigest';
import BriefingSummary from './components/BriefingSummary';
import { actCount } from './components/Headline';
import DetailPanel from './components/DetailPanel';
import Chat from './components/Chat';
import EvidenceDrawer from './components/EvidenceDrawer';
import ConfirmModal, { type ProposalDraft } from './components/ConfirmModal';
import FollowUps from './components/FollowUps';
import Watches from './components/Watches';
import WatchModal from './components/WatchModal';

const snapshot = fixtureJson as unknown as BriefingFixture;

const PAGE_TITLE: Record<Page, string> = {
  home: 'New chat',
  chat: 'Chat',
  briefing: 'Briefing',
  orders: 'Orders & output',
  actions: 'Actions',
  watches: 'Watches & alerts',
};

// How often the sidebar refreshes its follow-up counts, so a reminder or watch alert that the
// backend scheduler raised shows up without reloading the page.
const COUNTS_EVERY_MS = 30_000;

export default function App() {
  const [route, navigate] = useRoute();
  // The saved snapshot shows immediately; the live briefing replaces it once the backend answers.
  const [data, setData] = useState<BriefingFixture>(snapshot);
  const [source, setSource] = useState<BriefingSource>('checking');
  const [briefingError, setBriefingError] = useState<string | null>(null);
  const { briefing } = data;
  // Conversations live here so the sidebar list and the open chat stay in sync.
  const [sessions, setSessions] = useState<Session[]>([]);
  const [sessionsLoaded, setSessionsLoaded] = useState(false);
  const [sessionsError, setSessionsError] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [evidence, setEvidence] = useState<EvidenceView | null>(null);
  const [prefill, setPrefill] = useState<{ text: string; nonce: number } | null>(null);
  const [draft, setDraft] = useState<ProposalDraft | null>(null);
  const [watchOpen, setWatchOpen] = useState(false);
  const [counts, setCounts] = useState<FollowUpCounts | null>(null);
  // Bumped when something is saved, so the Actions and Watches pages reload.
  const [followUpsKey, setFollowUpsKey] = useState(0);
  const [toast, setToast] = useState<string | null>(null);

  const loadBriefing = useCallback(async () => {
    setSource('checking');
    try {
      setData(await api.latestBriefing());
      setBriefingError(null);
      setSource('live');
    } catch (e) {
      // Fall back to the snapshot and say so; never show stale live data as current.
      setData(snapshot);
      setBriefingError(e instanceof Error ? e.message : 'Unexpected error.');
      setSource('snapshot');
    }
  }, []);

  const loadSessions = useCallback(async () => {
    try {
      setSessions(await api.listSessions());
      setSessionsError(null);
    } catch (e) {
      setSessionsError(e instanceof Error ? e.message : 'Unexpected error.');
    } finally {
      setSessionsLoaded(true);
    }
  }, []);

  const loadCounts = useCallback(async () => {
    try {
      setCounts(await api.counts());
    } catch {
      setCounts(null); // backend offline: the sidebar simply shows no follow-up numbers
    }
  }, []);

  useEffect(() => {
    void loadBriefing();
    void loadSessions();
    void loadCounts();
    const timer = window.setInterval(() => void loadCounts(), COUNTS_EVERY_MS);
    return () => window.clearInterval(timer);
  }, [loadBriefing, loadSessions, loadCounts]);

  useEffect(() => {
    document.title = `${PAGE_TITLE[route.page]} · Manager Co-Pilot`;
    setMenuOpen(false);
  }, [route]);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 4000);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const followUpsChanged = useCallback(() => {
    void loadCounts();
    setFollowUpsKey((k) => k + 1);
  }, [loadCounts]);

  const saved = (message: string) => {
    setDraft(null);
    setWatchOpen(false);
    setToast(message);
    followUpsChanged();
  };

  // "Ask" buttons anywhere open a new conversation with the question typed in, not yet sent.
  const ask = useCallback(
    (text: string) => {
      setPrefill({ text, nonce: Date.now() });
      navigate({ page: 'home' });
    },
    [navigate],
  );
  const prefillUsed = useCallback(() => setPrefill(null), []);

  const sessionCreated = useCallback(
    (s: Session) => {
      setSessions((list) => [{ ...s, has_messages: true }, ...list.filter((x) => x.id !== s.id)]);
      navigate({ page: 'chat', sessionId: s.id }, { replace: true });
    },
    [navigate],
  );

  // Opening the dialog saves nothing; the backend saves only when the manager confirms.
  const propose = useCallback((d: ProposalDraft) => setDraft(d), []);

  const isChat = route.page === 'home' || route.page === 'chat';
  const chatId = route.page === 'chat' ? route.sessionId ?? null : null;

  let page;
  if (isChat) {
    // Home and an open conversation render the same Chat, so sending the first message
    // keeps the component (and its pending reply) while the address changes to #/chat/<id>.
    page = (
      <Chat
        sessionId={chatId}
        title={chatId ? sessions.find((s) => s.id === chatId)?.title : undefined}
        prefill={prefill}
        onPrefillUsed={prefillUsed}
        backendError={sessionsError}
        onRetry={() => {
          void loadSessions();
          void loadBriefing();
        }}
        onSessionCreated={sessionCreated}
        onTurnSettled={() => {
          void loadSessions();
          void loadCounts();
        }}
        onEvidence={setEvidence}
        onFollowUpsChanged={followUpsChanged}
        welcome={route.page === 'home' ? <TodayDigest fixture={data} source={source} /> : undefined}
        suggestions={route.page === 'home' ? suggestionsFor(briefing) : undefined}
      />
    );
  } else if (route.page === 'briefing') {
    page = (
      <div className="page">
        <BriefingSummary
          fixture={data}
          source={source}
          error={briefingError}
          onRefresh={() => void loadBriefing()}
          onEvidence={setEvidence}
          onAsk={ask}
          onPropose={propose}
        />
      </div>
    );
  } else if (route.page === 'orders') {
    page = (
      <div className="page">
        <header className="page-head">
          <h1>Orders &amp; output</h1>
          <p className="muted small">
            From the {briefing.as_of_date} briefing{source === 'snapshot' ? ' (saved snapshot)' : ''}. Open any row's
            evidence to see the source data.
          </p>
        </header>
        <DetailPanel
          briefing={briefing}
          onEvidence={setEvidence}
          onAsk={ask}
          onRemind={(o) =>
            propose({
              kind: 'reminder',
              order: { order_id: o.order_id, customer: o.customer, detail: `${o.current_stage} · ${o.risk_reasons.join('; ')}` },
              text: `Follow up on ${o.order_id} (${o.customer}): ${o.risk_reasons.join('; ')}.`,
              reason: `At-risk order in the ${briefing.as_of_date} briefing`,
            })
          }
        />
      </div>
    );
  } else if (route.page === 'watches') {
    page = (
      <div className="page">
        <Watches onNewWatch={() => setWatchOpen(true)} onChanged={followUpsChanged} refreshKey={followUpsKey} />
      </div>
    );
  } else {
    page = (
      <div className="page">
        <FollowUps
          onNewReminder={() => propose({ kind: 'reminder', text: '' })}
          onChanged={followUpsChanged}
          refreshKey={followUpsKey}
        />
      </div>
    );
  }

  return (
    <div className={`shell${menuOpen ? ' menu-open' : ''}`}>
      <Sidebar
        route={route}
        sessions={sessions}
        sessionsLoaded={sessionsLoaded}
        sessionsError={sessionsError}
        asOfDate={briefing.as_of_date}
        briefingSource={source}
        briefingDetail={
          source === 'live'
            ? `Generated ${new Date(data.generated_at).toLocaleString()} by ${data.generator}, backend ${data.backend_commit ?? 'unknown'}`
            : source === 'snapshot'
              ? `Saved snapshot from backend ${data.backend_commit ?? 'unknown'}. ${briefingError ?? ''}`.trim()
              : 'Loading the live briefing'
        }
        counts={{
          decisions: actCount(briefing),
          atRisk: briefing.at_risk.count,
          actions: counts ? counts.pending_proposals + counts.due_reminders : 0,
          alerts: counts?.unread_alerts ?? 0,
        }}
        onPick={() => setMenuOpen(false)}
      />
      {menuOpen && <div className="sidebar-scrim" onClick={() => setMenuOpen(false)} />}

      <div className="main-col">
        <header className="mobile-bar">
          <button className="btn btn-small" onClick={() => setMenuOpen(true)} aria-label="Open navigation">
            ☰ Menu
          </button>
          <span className="mobile-title">Manager Co-Pilot</span>
        </header>
        <main className={isChat ? 'main main-chat' : 'main'}>{page}</main>
      </div>

      <EvidenceDrawer view={evidence} rows={data.source_rows} onClose={() => setEvidence(null)} />

      {draft && <ConfirmModal draft={draft} onDone={saved} onClose={() => setDraft(null)} />}
      {watchOpen && <WatchModal onDone={saved} onClose={() => setWatchOpen(false)} />}
      {toast && (
        <div className="toast" role="status">
          {toast}
        </div>
      )}
    </div>
  );
}
