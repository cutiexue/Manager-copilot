import { useEffect, useState } from 'react';

// Reloads a page's data every 30 seconds while the tab is visible, and right away when the window
// comes back into focus, so an alert or reminder the backend scheduler raised shows up on its own.
// Returns the time of the last successful load, for the "Updated 11:33" line.
export const REFRESH_EVERY_MS = 30_000;

export function useAutoRefresh(load: () => Promise<boolean>, every = REFRESH_EVERY_MS): Date | null {
  const [updated, setUpdated] = useState<Date | null>(null);

  useEffect(() => {
    let alive = true;
    const run = async () => {
      if (document.visibilityState !== 'visible') return;
      if ((await load()) && alive) setUpdated(new Date());
    };
    void run();
    const timer = window.setInterval(() => void run(), every);
    const onFocus = () => void run();
    window.addEventListener('focus', onFocus);
    document.addEventListener('visibilitychange', onFocus);
    return () => {
      alive = false;
      window.clearInterval(timer);
      window.removeEventListener('focus', onFocus);
      document.removeEventListener('visibilitychange', onFocus);
    };
  }, [load, every]);

  return updated;
}

export const clock = (d: Date) => d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
