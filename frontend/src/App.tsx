import { useCallback, useEffect, useState } from 'react';
import fixtureJson from './fixtures/briefing.json';
import { api } from './api';
import type { ActionProposal, BriefingFixture, BriefingSource, EvidenceView } from './types';
import BriefingSummary from './components/BriefingSummary';
import DetailPanel from './components/DetailPanel';
import Chat from './components/Chat';
import EvidenceDrawer from './components/EvidenceDrawer';
import ConfirmModal, { type ProposalDraft } from './components/ConfirmModal';
import ActionLog from './components/ActionLog';

const snapshot = fixtureJson as unknown as BriefingFixture;

export default function App() {
  // The saved snapshot shows immediately; the live briefing replaces it once the backend answers.
  const [data, setData] = useState<BriefingFixture>(snapshot);
  const [source, setSource] = useState<BriefingSource>('checking');
  const [briefingError, setBriefingError] = useState<string | null>(null);
  const { briefing } = data;
  const [evidence, setEvidence] = useState<EvidenceView | null>(null);
  const [prefill, setPrefill] = useState<{ text: string; nonce: number } | null>(null);
  const [draft, setDraft] = useState<ProposalDraft | null>(null);
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

  useEffect(() => {
    void loadBriefing();
  }, [loadBriefing]);

  const ask = useCallback((text: string) => setPrefill({ text, nonce: Date.now() }), []);

  const propose = useCallback((d: ProposalDraft) => {
    // Step 1 of the plan's state machine: the proposal exists but nothing is executed yet.
    const p: ActionProposal = {
      id: `ACT-${String(Date.now()).slice(-6)}`,
      kind: d.kind,
      target: d.target,
      text: d.text,
      state: 'PROPOSED',
      created_at: new Date().toISOString(),
    };
    setActions((a) => [p, ...a]);
    setDraft({ ...d, proposalId: p.id });
  }, []);

  const decide = (id: string, state: 'CONFIRMED' | 'CANCELLED', text?: string) => {
    setActions((a) =>
      a.map((p) => (p.id === id ? { ...p, state, text: text ?? p.text, decided_at: new Date().toISOString() } : p)),
    );
    setDraft(null);
  };

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo" aria-hidden>◆</span>
          <div>
            <h1>Manager Co-Pilot</h1>
            <p className="muted">SweaterCo · General Manager view</p>
          </div>
        </div>
        <div className="clock" title="Business analysis uses the dataset clock, not today's date.">
          <span className="pill">Data as of {briefing.as_of_date}</span>
          <span className={source === 'live' ? 'pill' : 'pill pill-warn'}>
            {source === 'live' ? 'Briefing: live' : source === 'checking' ? 'Briefing: checking…' : 'Briefing: snapshot'}
          </span>
        </div>
      </header>

      <BriefingSummary
        fixture={data}
        source={source}
        error={briefingError}
        onRefresh={() => void loadBriefing()}
        onEvidence={setEvidence}
        onAsk={ask}
        onPropose={(d) => propose(d)}
      />

      <main className="workspace">
        <Chat prefill={prefill} />
        <DetailPanel briefing={briefing} onEvidence={setEvidence} onAsk={ask} />
      </main>

      <ActionLog actions={actions} />

      <EvidenceDrawer view={evidence} rows={data.source_rows} onClose={() => setEvidence(null)} />

      {draft && draft.proposalId && (
        <ConfirmModal
          draft={draft}
          onConfirm={(text) => decide(draft.proposalId!, 'CONFIRMED', text)}
          onCancel={() => decide(draft.proposalId!, 'CANCELLED')}
        />
      )}
    </div>
  );
}
