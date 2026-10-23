import { useCallback, useEffect, useState } from 'react';
import fixtureJson from './fixtures/briefing.json';
import { api } from './api';
import { useRoute, type Page } from './route';
import type { ActionProposal, BriefingFixture, BriefingSource, EvidenceView, Session } from './types';
import Sidebar from './components/Sidebar';
import TodayDigest, { suggestionsFor } from './components/TodayDigest';
import BriefingSummary from './components/BriefingSummary';
import DetailPanel from './components/DetailPanel';
import Chat from './components/Chat';
import EvidenceDrawer from './components/EvidenceDrawer';
import ConfirmModal, { type ProposalDraft } from './components/ConfirmModal';
import ActionLog from './components/ActionLog';

const snapshot = fixtureJson as unknown as BriefingFixture;

const PAGE_TITLE: Record<Page, string> = {
  home: 'New chat',
  chat: 'Chat',
  briefing: 'Briefing',
  orders: 'Orders & output',
  actions: 'Actions',
};

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
  const [draftOpenedAt, setDraftOpenedAt] = useState('');
  const [actions, setActions] = useState<ActionProposal[]>([]);

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

  useEffect(() => {
    void loadBriefing();
    void loadSessions();
  }, [loadBriefing, loadSessions]);

  useEffect(() => {
    document.title = `${PAGE_TITLE[route.page]} · Manager Co-Pilot`;
    setMenuOpen(false);
  }, [route]);

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

  // Opening the dialog is a draft; nothing is recorded or executed until the manager decides.
  const propose = useCallback((d: ProposalDraft) => {
    setDraft(d);
    setDraftOpenedAt(new Date().toISOString());
  }, []);

  const decide = (state: 'CONFIRMED' | 'CANCELLED', target: string, text: string) => {
    const p: ActionProposal = {
      id: `ACT-${String(Date.now()).slice(-6)}`,
      kind: draft?.kind ?? 'reminder',
      target,
      text,
      state,
      created_at: draftOpenedAt,
      decided_at: new Date().toISOString(),
    };
    setActions((a) => [p, ...a]);
    setDraft(null);
  };

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
        onTurnSettled={() => void loadSessions()}
        welcome={
          route.page === 'home' ? (
            <TodayDigest fixture={data} source={source} />
          ) : undefined
        }
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
  } else {
    page = (
      <div className="page">
        <ActionLog actions={actions} onNewReminder={() => propose({ kind: 'reminder', text: '' })} />
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
          decisions: briefing.review_count ?? briefing.decisions.length,
          atRisk: briefing.at_risk.count,
          actions: actions.length,
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

      {draft && (
        <ConfirmModal
          draft={draft}
          onConfirm={(target, text) => decide('CONFIRMED', target, text)}
          // Closing before choosing what the reminder is about leaves nothing to record.
          onCancel={(target, text) => (target ? decide('CANCELLED', target, text) : setDraft(null))}
        />
      )}
    </div>
  );
}
