import { useCallback, useEffect, useMemo, useState } from 'react';
import fixtureJson from './fixtures/briefing.json';
import { api } from './api';
import { useRoute, type Page } from './route';
import { useTheme } from './theme';
import type { BriefingFixture, BriefingSource, EvidenceView, FollowUpCounts, Session } from './types';
import TopBar from './components/TopBar';
import Dock from './components/Dock';
import ChatSidebar from './components/ChatSidebar';
import CommandPalette, { type Command } from './components/CommandPalette';
import OrdersPage from './components/OrdersPage';
import TodayDigest, { suggestionsFor } from './components/TodayDigest';
import BriefingSummary from './components/BriefingSummary';
import { actCount } from './components/Headline';
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
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [theme, setTheme] = useTheme();
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
  }, [route]);

  // Ctrl+K (⌘K on a Mac) opens search from anywhere; pressing it again closes it.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setPaletteOpen((o) => !o);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

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
        <OrdersPage
          onEvidence={setEvidence}
          onAsk={ask}
          onRemind={(o) =>
            propose({
              kind: 'reminder',
              order: { order_id: o.order_id, customer: o.customer, detail: `${o.current_stage}${o.risk_reasons.length ? ` · ${o.risk_reasons.join('; ')}` : ''}` },
              text: `Follow up on ${o.order_id} (${o.customer})${o.risk_reasons.length ? `: ${o.risk_reasons.join('; ')}` : ''}.`,
              reason: `From the Orders page, data as of ${briefing.as_of_date}`,
            })
          }
        />
      </div>
    );
  } else if (route.page === 'watches') {
    page = (
      <div className="page">
        <Watches
          onNewWatch={() => setWatchOpen(true)}
          // Loading a snapshot moves the whole app to that day, so the briefing and its date reload too.
          onChanged={() => { followUpsChanged(); void loadBriefing(); }}
          refreshKey={followUpsKey}
        />
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

  const commands = useMemo<Command[]>(() => {
    const go = (p: Page) => () => navigate({ page: p });
    return [
      { id: 'new', label: 'New chat', group: 'Pages', icon: 'plus', run: go('home') },
      { id: 'briefing', label: 'Morning briefing', group: 'Pages', icon: 'briefing', run: go('briefing') },
      { id: 'orders', label: 'Orders & output', group: 'Pages', icon: 'orders', run: go('orders') },
      { id: 'actions', label: 'Actions: reminders, notes and drafts', group: 'Pages', icon: 'actions', run: go('actions') },
      { id: 'watches', label: 'Watches & alerts', group: 'Pages', icon: 'watch', run: go('watches') },
      { id: 'reminder', label: 'New reminder…', group: 'Actions', icon: 'remind', run: () => propose({ kind: 'reminder', text: '' }) },
      { id: 'watch', label: 'New watch…', group: 'Actions', icon: 'watch', run: () => setWatchOpen(true) },
      { id: 'light', label: 'Theme: light', group: 'Actions', icon: 'sun', run: () => setTheme('light') },
      { id: 'dark', label: 'Theme: dark', group: 'Actions', icon: 'moon', run: () => setTheme('dark') },
      { id: 'system', label: 'Theme: match system', group: 'Actions', icon: 'monitor', run: () => setTheme('system') },
      ...sessions
        .filter((s) => s.has_messages !== false)
        .slice(0, 30)
        .map((s): Command => ({
          id: `chat-${s.id}`, label: s.title, group: 'Conversations', icon: 'chats',
          run: () => navigate({ page: 'chat', sessionId: s.id }),
        })),
    ];
  }, [navigate, propose, sessions, setTheme]);

  return (
    <div className="shell">
      <div className="backdrop" aria-hidden />
      <TopBar
        asOfDate={briefing.as_of_date}
        briefingSource={source}
        briefingDetail={
          source === 'live'
            ? `Generated ${new Date(data.generated_at).toLocaleString()} by ${data.generator}, backend ${data.backend_commit ?? 'unknown'}`
            : source === 'snapshot'
              ? `Saved snapshot from backend ${data.backend_commit ?? 'unknown'}. ${briefingError ?? ''}`.trim()
              : 'Loading the live briefing'
        }
        onSearch={() => setPaletteOpen(true)}
        theme={theme}
        setTheme={setTheme}
      />
      <main className={isChat ? 'main main-chat' : 'main'}>
        {isChat && (
          <ChatSidebar route={route} sessions={sessions} sessionsLoaded={sessionsLoaded} sessionsError={sessionsError} />
        )}
        {page}
      </main>
      <Dock
        route={route}
        sessions={sessions}
        sessionsLoaded={sessionsLoaded}
        sessionsError={sessionsError}
        counts={{
          decisions: actCount(briefing),
          atRisk: briefing.at_risk.count,
          actions: counts ? counts.pending_proposals + counts.due_reminders : 0,
          alerts: counts?.unread_alerts ?? 0,
        }}
      />

      <EvidenceDrawer view={evidence} rows={data.source_rows} onClose={() => setEvidence(null)} />

      {draft && <ConfirmModal draft={draft} onDone={saved} onClose={() => setDraft(null)} />}
      {watchOpen && <WatchModal onDone={saved} onClose={() => setWatchOpen(false)} />}
      {paletteOpen && <CommandPalette commands={commands} onClose={() => setPaletteOpen(false)} />}
      {toast && (
        <div className="toast" role="status">
          {toast}
        </div>
      )}
    </div>
  );
}
