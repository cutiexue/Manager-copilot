import { type ReactNode, useEffect, useRef, useState } from 'react';
import { api } from '../api';
import type { AnswerCheck, ChatMessage, EvidenceView, Proposal, Session } from '../types';
import Icon from './Icon';
import Markdown from './Markdown';
import ProposalCard from './ProposalCard';
import { useDictation, useSpeaker, useVoicePrefs } from '../useVoice';
import { chatAttemptFor, sendChatAttempt, type ChatAttempt } from '../chatRetry';

interface Props {
  /** null = a new conversation, created on the first message */
  sessionId: string | null;
  title?: string;
  prefill: { text: string; nonce: number } | null;
  onPrefillUsed: () => void;
  /** Error from loading the conversation list, e.g. the backend is offline */
  backendError: string | null;
  onRetry: () => void;
  onSessionCreated: (session: Session) => void;
  /** Called after every send, successful or not, so the conversation list can refresh */
  onTurnSettled: () => void;
  /** Shown above the chat box while the conversation is empty (the Home page) */
  welcome?: ReactNode;
  suggestions?: string[];
  /** Opens the evidence drawer for an answer's cited rows */
  onEvidence: (view: EvidenceView) => void;
  /** A proposal was confirmed or cancelled, so follow-up counts may have changed */
  onFollowUpsChanged: () => void;
}

const args = (values: Record<string, unknown>) =>
  Object.entries(values)
    .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
    .join(', ') || '—';

/** What the evidence drawer shows for one answer: the tools it called and the rows they cited. */
function evidenceFor(m: ChatMessage): EvidenceView {
  const first = m.content.split('\n').find((line) => line.trim()) ?? '';
  return {
    title: 'this answer',
    claim: first.replace(/[*`#|]/g, '').trim().slice(0, 240),
    calculation: (m.tool_calls ?? []).map((c) => ({ label: c.name, value: `${args(c.arguments)}${c.status ? ` → ${c.status}` : ''}` })),
    calculationTitle: 'Tool calls',
    toolResults: (m.tool_calls ?? []).flatMap((c) => c.result ? [{ name: c.name, result: c.result }] : []),
    dataVersion: m.evidence?.data_version,
    dataDate: m.evidence?.data_date,
    warnings: m.evidence?.warnings,
    refs: m.evidence?.refs ?? [],
    rows: m.evidence?.rows,
  };
}

type Status = 'idle' | 'loading' | 'sending' | 'error';

// api.ts uses this wording when the backend process cannot be reached.
const OFFLINE_PREFIX = 'Cannot reach';

export default function Chat({
  sessionId, title, prefill, onPrefillUsed, backendError, onRetry, onSessionCreated, onTurnSettled, welcome, suggestions,
  onEvidence, onFollowUpsChanged,
}: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [status, setStatus] = useState<Status>('idle');
  const [error, setError] = useState<string | null>(null);
  // The message whose send just failed; Retry sends it again.
  const [failed, setFailed] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  // The conversation on screen; an answer that arrives after switching away is dropped.
  const shown = useRef<string | null>(sessionId);
  // A conversation this component just created already has its first message on screen,
  // so the history request for its new address is skipped once.
  const createdHere = useRef<string | null>(null);
  const attemptRef = useRef<ChatAttempt | null>(null);
  const requestScope = useRef(0);
  const mounted = useRef(true);
  // Voice: dictation fills the chat box (it never sends); answers can be read aloud.
  const voice = useVoicePrefs();
  const dictation = useDictation(voice.lang, setInput);
  const speaker = useSpeaker(voice.lang);
  const autoRead = useRef(voice.autoRead);
  autoRead.current = voice.autoRead;
  const { stop: stopSpeaking } = speaker;

  const fail = (e: unknown) => {
    setError(e instanceof Error ? e.message : 'Unexpected error.');
    setStatus('error');
  };

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      requestScope.current += 1;
    };
  }, []);

  useEffect(() => {
    shown.current = sessionId;
    if (sessionId !== null && sessionId === createdHere.current) {
      createdHere.current = null;
      return;
    }
    requestScope.current += 1;
    attemptRef.current = null;
    if (sessionId === null) {
      setMessages([]);
      setError(null);
      setFailed(null);
      setStatus('idle');
      return;
    }
    let cancelled = false;
    setStatus('loading');
    setError(null);
    setFailed(null);
    api.history(sessionId).then(
      (history) => {
        if (cancelled) return;
        setMessages(history);
        setStatus('idle');
      },
      (e) => {
        if (cancelled) return;
        setMessages([]);
        fail(e);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [sessionId, reload]);

  // Leaving a conversation stops its answer being read.
  useEffect(() => stopSpeaking, [sessionId, stopSpeaking]);

  useEffect(() => {
    if (!prefill) return;
    setInput(prefill.text);
    inputRef.current?.focus();
    onPrefillUsed();
  }, [prefill, onPrefillUsed]);

  useEffect(() => {
    if (messages.length > 0) endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, status]);

  const send = async (again?: string) => {
    const text = (again ?? input).trim();
    if (!text || status === 'sending' || status === 'loading') return;
    let id = sessionId;
    const scope = requestScope.current;
    const isCurrent = () => mounted.current && requestScope.current === scope && shown.current === id;
    const attempt = chatAttemptFor(attemptRef, id, text);
    const answerIndex = messages.length + 1;
    dictation.cancel();
    speaker.stop();
    setError(null);
    setFailed(null);
    setStatus('sending');
    setMessages((m) => [...m, { role: 'human', content: text }]);
    setInput('');
    try {
      const res = await sendChatAttempt(attempt, api, (created) => {
        const stillHere = isCurrent();
        id = created.id;
        if (stillHere) {
          createdHere.current = id;
          shown.current = id;
          onSessionCreated(created);
        }
      });
      if (isCurrent()) {
        setMessages((m) => [
          ...m,
          { role: 'ai', content: res.answer, tool_calls: res.tool_calls, evidence: res.evidence, proposals: res.proposals,
            answer_check: res.answer_check },
        ]);
        setStatus('idle');
        if (autoRead.current) speaker.speak(String(answerIndex), res.answer);
      }
    } catch (e) {
      if (isCurrent()) {
        // The response may have been lost after commit. Remove only the optimistic UI
        // message; Retry retains this intent's ID and recovers the original saved response.
        setMessages((m) => m.slice(0, -1));
        setInput(text);
        setFailed(text);
        fail(e);
      }
    } finally {
      onTurnSettled();
    }
  };

  const proposalChanged = (next: Proposal) => {
    setMessages((list) =>
      list.map((m) => (m.proposals ? { ...m, proposals: m.proposals.map((p) => (p.id === next.id ? next : p)) } : m)),
    );
    onFollowUpsChanged();
  };

  const retry = () => {
    if (failed) {
      void send(failed);
      return;
    }
    setError(null);
    setStatus('idle');
    setReload((n) => n + 1);
    onRetry();
  };

  const empty = messages.length === 0 && status !== 'loading';
  const problem = error ?? backendError;
  const offline = problem?.startsWith(OFFLINE_PREFIX) ?? false;

  return (
    <section className={`chat ${empty ? 'chat-empty' : 'chat-thread'}`} aria-label="Chat with Co-Pilot">
      <div className="chat-scroll">
        <div className="chat-column">
          {empty ? (
            welcome ?? <p className="empty">No messages in this conversation yet.</p>
          ) : (
            <>
              {title && <h2 className="chat-title">{title}</h2>}
              {status === 'loading' && <p className="muted">Loading…</p>}
              <div className="messages" aria-live="polite">
                {messages.map((m, i) => (
                  <div key={i} className={`msg msg-${m.role}`}>
                    <span className="who">{m.role === 'human' ? 'You' : 'Co-Pilot'}</span>
                    {m.role === 'ai' ? (
                      <div className="bubble bubble-md">
                        <Markdown text={m.content} />
                      </div>
                    ) : (
                      <div className="bubble">{m.content}</div>
                    )}
                    {m.proposals?.map((p) => <ProposalCard key={p.id} proposal={p} onChanged={proposalChanged} />)}
                    {m.role === 'ai' && (
                      <div className="msg-tools">
                        {m.evidence && (m.evidence.refs.length > 0 || (m.tool_calls?.length ?? 0) > 0) && (
                          <button className="btn btn-ghost btn-small" onClick={() => onEvidence(evidenceFor(m))}>
                            <Icon name="evidence" size={14} /> Evidence{m.evidence.refs.length > 0 ? ` (${m.evidence.refs.length})` : ''}
                          </button>
                        )}
                        {speaker.supported && (
                          <button className="btn btn-ghost btn-small"
                            onClick={() => (speaker.speaking === String(i) ? speaker.stop() : speaker.speak(String(i), m.content))}>
                            <Icon name={speaker.speaking === String(i) ? 'stop' : 'speaker'} size={14} />
                            {speaker.speaking === String(i) ? 'Stop' : 'Read aloud'}
                          </button>
                        )}
                      </div>
                    )}
                    {m.role === 'ai' && <CheckNote check={m.answer_check} />}
                  </div>
                ))}
                {status === 'sending' && (
                  <div className="msg msg-ai">
                    <span className="who">Co-Pilot</span>
                    <div className="bubble muted">Looking up the data…</div>
                  </div>
                )}
                <div ref={endRef} />
              </div>
            </>
          )}
        </div>
      </div>

      <div className="chat-dock">
        <div className="chat-column">
          {problem && (
            <div className="alert" role="alert">
              <strong>{offline ? 'Backend offline.' : 'Request failed.'}</strong> {problem}
              <button className="btn btn-small" onClick={retry}>
                <Icon name="refresh" size={14} /> Retry
              </button>
            </div>
          )}

          <form
            className="composer"
            onSubmit={(e) => {
              e.preventDefault();
              void send();
            }}
          >
            <textarea
              ref={inputRef}
              value={input}
              rows={empty ? 3 : 2}
              maxLength={20000}
              placeholder={empty ? 'Ask about orders, customers or production…' : 'Ask a follow-up…'}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  void send();
                }
              }}
              aria-label="Message"
            />
            {dictation.supported && (
              <button
                type="button"
                className={`btn btn-ghost mic${dictation.listening ? ' mic-on' : ''}`}
                onClick={() => {
                  if (dictation.listening) {
                    dictation.stop();
                  } else {
                    speaker.stop();
                    dictation.start(input);
                    inputRef.current?.focus();
                  }
                }}
                disabled={status === 'sending'}
                aria-label={dictation.listening ? 'Stop voice input' : 'Voice input'}
                title={dictation.listening ? 'Stop voice input' : 'Voice input · browser speech service'}
              >
                <Icon name={dictation.listening ? 'stop' : 'mic'} size={18} />
              </button>
            )}
            <button className="btn btn-primary" type="submit" disabled={!input.trim() || status === 'sending' || status === 'loading'}>
              Send
            </button>
          </form>

          {empty && suggestions && suggestions.length > 0 && (
            <div className="chips" aria-label="Suggested questions">
              {suggestions.map((s) => (
                <button
                  key={s}
                  type="button"
                  className="chip"
                  onClick={() => {
                    setInput(s);
                    inputRef.current?.focus();
                  }}
                >
                  {s}
                </button>
              ))}
            </div>
          )}
          {(dictation.supported || speaker.supported) && (
            <div className="voice-bar small">
              {dictation.supported && (
                <label className="voice-lang">
                  <Icon name="mic" size={14} />
                  <select value={voice.lang} aria-label="Voice input language"
                    onChange={(e) => voice.setLang(e.target.value)}>
                    {voice.options.map((l) => (
                      <option key={l.code} value={l.code}>{l.label}</option>
                    ))}
                  </select>
                </label>
              )}
              {speaker.supported && (
                <label className="voice-auto">
                  <input type="checkbox" checked={voice.autoRead} onChange={(e) => {
                    voice.setAutoRead(e.target.checked);
                    if (!e.target.checked) speaker.stop();
                  }} />
                  Read answers aloud
                </label>
              )}
              {dictation.listening && <span className="voice-status" role="status">Listening…</span>}
              {dictation.error && <span className="voice-status" role="status">{dictation.error}</span>}
              {speaker.missing && <span className="voice-status" role="status">No {speaker.missing} voice on this device</span>}
            </div>
          )}
          <p className="hint small muted">
            Open Evidence to review the sources and results used in an answer. Enter to send, Shift+Enter for a new line.
          </p>
        </div>
      </div>
    </section>
  );
}

// A value-presence check, not a semantic correctness verdict.
function CheckNote({ check }: { check?: AnswerCheck }) {
  if (!check) return null;
  if (check.checked === 0) return <p className="check-note small">No supported values were checked. This is not a factual verification.</p>;
  if (check.unverified.length === 0) {
    return <p className="check-note small">{check.checked} supported values checked; no unmatched values found. Sources can include your request. Meaning, small counts and value-to-order links other than overdue days are not verified.</p>;
  }
  return (
    <p className="check-note check-warn small" role="note">
      Values not matched to the available sources: {check.unverified.map((u) => u.text).join(', ')}. Review the evidence;
      this check can miss semantic errors and flag formatting differences.
    </p>
  );
}
