import { type ReactNode, useEffect, useRef, useState } from 'react';
import { api } from '../api';
import type { ChatMessage, Session } from '../types';
import Icon from './Icon';

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
}

type Status = 'idle' | 'loading' | 'sending' | 'error';

// api.ts uses this wording when the backend process cannot be reached.
const OFFLINE_PREFIX = 'Cannot reach';

export default function Chat({
  sessionId, title, prefill, onPrefillUsed, backendError, onRetry, onSessionCreated, onTurnSettled, welcome, suggestions,
}: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [status, setStatus] = useState<Status>('idle');
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);
  // The conversation on screen; an answer that arrives after switching away is dropped.
  const shown = useRef<string | null>(sessionId);
  // A conversation this component just created already has its first message on screen,
  // so the history request for its new address is skipped once.
  const createdHere = useRef<string | null>(null);

  const fail = (e: unknown) => {
    setError(e instanceof Error ? e.message : 'Unexpected error.');
    setStatus('error');
  };

  useEffect(() => {
    shown.current = sessionId;
    if (sessionId === null) {
      setMessages([]);
      setError(null);
      setStatus('idle');
      return;
    }
    if (sessionId === createdHere.current) {
      // Only the switch to the address of the just-created conversation is skipped;
      // coming back to it later loads its history like any other conversation.
      createdHere.current = null;
      return;
    }
    let cancelled = false;
    setStatus('loading');
    setError(null);
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

  useEffect(() => {
    if (!prefill) return;
    setInput(prefill.text);
    inputRef.current?.focus();
    onPrefillUsed();
  }, [prefill, onPrefillUsed]);

  useEffect(() => {
    if (messages.length > 0) endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, status]);

  const send = async () => {
    const text = input.trim();
    if (!text || status === 'sending') return;
    let id = sessionId;
    setError(null);
    setStatus('sending');
    setMessages((m) => [...m, { role: 'human', content: text }]);
    setInput('');
    try {
      if (!id) {
        const created = await api.createSession(text.slice(0, 60));
        id = created.id;
        createdHere.current = id;
        shown.current = id;
        onSessionCreated(created);
      }
      const res = await api.send(id, text);
      if (shown.current === id) {
        setMessages((m) => [...m, { role: 'ai', content: res.answer }]);
        setStatus('idle');
      }
    } catch (e) {
      if (shown.current === id) {
        // The backend keeps history unchanged on failure, so drop the optimistic message.
        setMessages((m) => m.slice(0, -1));
        setInput(text);
        fail(e);
      }
    } finally {
      onTurnSettled();
    }
  };

  const retry = () => {
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
                    <div className="bubble">{m.content}</div>
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
            <button className="btn btn-primary" type="submit" disabled={!input.trim() || status === 'sending'}>
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
          <p className="hint small muted">
            Every answer is looked up fresh from the data. Enter to send, Shift+Enter for a new line.
          </p>
        </div>
      </div>
    </section>
  );
}
