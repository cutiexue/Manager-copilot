import { useCallback, useEffect, useState } from 'react';

// Hash routes (#/briefing, #/chat/<id>) keep the current page on refresh and make the
// browser back button work, without adding a router dependency.

export type Page = 'home' | 'chat' | 'chats' | 'briefing' | 'orders' | 'actions' | 'watches';

export interface Route {
  page: Page;
  /** Only for page 'chat' */
  sessionId?: string;
}

// Conversation IDs are UUIDs (backend/storage.py). Anything else in the address is ignored, so a
// crafted link cannot steer a request to another endpoint, and a bad "%" escape cannot crash the page.
const SESSION_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function decodeSessionId(raw: string): string | null {
  try {
    const id = decodeURIComponent(raw);
    return SESSION_ID.test(id) ? id : null;
  } catch {
    return null;
  }
}

export function parseHash(hash: string): Route {
  const [, page = '', raw] = hash.replace(/^#/, '').split('/');
  const id = page === 'chat' && raw ? decodeSessionId(raw) : null;
  if (id) return { page: 'chat', sessionId: id };
  if (page === 'chats' || page === 'briefing' || page === 'orders' || page === 'actions' || page === 'watches') return { page };
  return { page: 'home' };
}

export function hrefFor(route: Route): string {
  if (route.page === 'chat' && route.sessionId) return `#/chat/${encodeURIComponent(route.sessionId)}`;
  return route.page === 'home' || route.page === 'chat' ? '#/' : `#/${route.page}`;
}

export function useRoute(): [Route, (route: Route, options?: { replace?: boolean }) => void] {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash));

  useEffect(() => {
    const onChange = () => setRoute(parseHash(window.location.hash));
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);

  const navigate = useCallback((next: Route, options?: { replace?: boolean }) => {
    const href = hrefFor(next);
    if (options?.replace) {
      // replaceState does not fire hashchange, so update the state directly.
      window.history.replaceState(null, '', href);
      setRoute(parseHash(href));
    } else if (window.location.hash !== href) {
      window.location.hash = href;
    } else {
      setRoute(parseHash(href));
    }
  }, []);

  return [route, navigate];
}
