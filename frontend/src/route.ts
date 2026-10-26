import { useCallback, useEffect, useState } from 'react';

// Hash routes (#/briefing, #/chat/<id>) keep the current page on refresh and make the
// browser back button work, without adding a router dependency.

export type Page = 'home' | 'chat' | 'briefing' | 'orders' | 'actions' | 'watches';

export interface Route {
  page: Page;
  /** Only for page 'chat' */
  sessionId?: string;
}

export function parseHash(hash: string): Route {
  const [, page = '', id] = hash.replace(/^#/, '').split('/');
  if (page === 'chat' && id) return { page: 'chat', sessionId: decodeURIComponent(id) };
  if (page === 'briefing' || page === 'orders' || page === 'actions' || page === 'watches') return { page };
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
