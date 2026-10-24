import type { BriefingFixture, ChatMessage, OrderSearchResult, SendMessageResponse, Session } from './types';

// All calls go through the Vite proxy (/api -> backend). See vite.config.ts.
const BASE = '/api';

const UNREACHABLE = 'Cannot reach the backend. Start it with `python main.py --api`.';

export class ApiError extends Error {
  /** `code` is the backend's stable error name (e.g. SESSION_NOT_FOUND); null when it did not answer. */
  constructor(message: string, readonly status: number | null, readonly code: string | null = null) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(BASE + path, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(UNREACHABLE, null);
  }
  if (!res.ok) {
    // The backend always answers errors as JSON {detail, code}; anything else came from the Vite
    // proxy, which answers 5xx itself when the backend process is down.
    let detail: string | null = null;
    let code: string | null = null;
    try {
      const body = await res.json();
      if (typeof body?.detail === 'string') detail = body.detail;
      if (typeof body?.code === 'string') code = body.code;
    } catch {
      /* non-JSON error body */
    }
    if (detail === null && res.status >= 500) throw new ApiError(UNREACHABLE, res.status);
    throw new ApiError(detail ?? res.statusText, res.status, code);
  }
  return res.json() as Promise<T>;
}

export const api = {
  latestBriefing: () => request<BriefingFixture>('/briefings/latest'),
  searchOrders: (query: string, limit = 8) =>
    request<OrderSearchResult>(`/orders/search?q=${encodeURIComponent(query)}&limit=${limit}`),
  listSessions: () => request<Session[]>('/sessions'),
  createSession: (title: string) =>
    request<Session>('/sessions', { method: 'POST', body: JSON.stringify({ title }) }),
  history: (sessionId: string) => request<ChatMessage[]>(`/sessions/${sessionId}/messages`),
  send: (sessionId: string, message: string) =>
    request<SendMessageResponse>(`/sessions/${sessionId}/messages`, {
      method: 'POST',
      body: JSON.stringify({ message }),
    }),
};
