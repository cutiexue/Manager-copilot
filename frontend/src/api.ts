import type { BriefingFixture, ChatMessage, OrderSearchResult, SendMessageResponse, Session } from './types';

// All calls go through the Vite proxy (/api -> backend). See vite.config.ts.
const BASE = '/api';

export class ApiError extends Error {
  constructor(message: string, readonly status: number | null) {
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
    throw new ApiError('Cannot reach the backend. Start it with `python main.py --api`.', null);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (typeof body?.detail === 'string') detail = body.detail;
    } catch {
      /* non-JSON error body */
    }
    // The Vite proxy answers 500/502/504 when the backend process is down.
    if (res.status === 502 || res.status === 504 || (res.status === 500 && detail === 'Internal Server Error')) {
      throw new ApiError('Cannot reach the backend. Start it with `python main.py --api`.', res.status);
    }
    throw new ApiError(detail, res.status);
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
