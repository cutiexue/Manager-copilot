import { useEffect, useRef, useState } from 'react';
import { api, ApiError } from '../api';
import type { ChatMessage, Session } from '../types';

interface Props {
  prefill: { text: string; nonce: number } | null;
}

type Status = 'idle' | 'loading' | 'sending' | 'error';

export default function Chat({ prefill }: Props) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [status, setStatus] = useState<Status>('loading');
  const [error, setError] = useState<string | null>(null);
  const [offline, setOffline] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);

  const fail = (e: unknown) => {
    const msg = e instanceof Error ? e.message : 'Unexpected error.';
    setOffline(e instanceof ApiError && msg.startsWith('Cannot reach'));
    setError(msg);
    setStatus('error');
  };

  const loadSessions = async () => {
    setStatus('loading');
    setError(null);
    try {
      setSessions(await api.listSessions());
      setOffline(false);
      setStatus('idle');
    } catch (e) {
      fail(e);
    }
  };

  useEffect(() => {
    void loadSessions();
  }, []);

  useEffect(() => {
    if (prefill) {
      setInput(prefill.text);
      inputRef.current?.focus();
    }
  }, [prefill]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, status]);

  const openSession = async (id: string) => {
    if (!id) {
      setSessionId(null);
      setMessages([]);
      return;
    }
    setStatus('loading');
    try {
      setMessages(await api.history(id));
      setSessionId(id);
      setStatus('idle');
    } catch (e) {
      fail(e);
    }
  };

  const send = async () => {
    const text = input.trim();
    if (!text || status === 'sending') return;
    setError(null);
    setStatus('sending');
    setMessages((m) => [...m, { role: 'human', content: text }]);
    setInput('');
    try {
      let id = sessionId;
      if (!id) {
        const s = await api.createSession(text.slice(0, 60));
        id = s.id;
        setSessionId(id);
        setSessions((list) => [s, ...list]);
      }
      const res = await api.send(id, text);
      setMessages((m) => [...m, { role: 'ai', content: res.answer }]);
      setStatus('idle');
    } catch (e) {
      // The backend keeps history unchanged on failure, so drop the optimistic message.
      setMessages((m) => m.slice(0, -1));
      setInput(text);
      fail(e);
    }
  };

  return (
    <section className="panel chat" aria-label="Chat with Co-Pilot">
      <div className="chat-head">
        <h2>Ask Co-Pilot</h2>
        <label className="small">
          <span className="sr-only">Conversation</span>
          <select value={sessionId ?? ''} onChange={(e) => void openSession(e.target.value)} disabled={offline}>
            <option value="">New conversation</option>
            {sessions.map((s) => (
              <option key={s.id} value={s.id}>
                {s.title}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="messages" aria-live="polite">
        {status === 'loading' && <p className="muted">Loading…</p>}
        {messages.length === 0 && status !== 'loading' && !offline && (
          <div className="empty">
            <p>Ask about orders, customers or production. Every answer is looked up fresh from the data.</p>
            <p className="small muted">Try: “Which TrendCart orders are overdue?” or “How did ASSEMBLY do yesterday?”</p>
          </div>
        )}
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

      {error && (
        <div className="alert" role="alert">
          <strong>{offline ? 'Backend offline.' : 'Request failed.'}</strong> {error}
          <button className="btn btn-small" onClick={() => void loadSessions()}>
            Retry
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
          rows={2}
          maxLength={20000}
          placeholder="Ask a question…  (Enter to send, Shift+Enter for a new line)"
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
    </section>
  );
}
