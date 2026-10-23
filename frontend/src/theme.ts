import { useEffect, useState } from 'react';

// Light, dark, or follow the system appearance (the default). The choice is kept in this browser
// only. index.html runs the same rule before the first paint, so a saved choice never flashes the
// other theme while the app loads; keep the two in step.
export type ThemeChoice = 'light' | 'dark' | 'system';

const KEY = 'manager-copilot-theme';
const systemDark = () => window.matchMedia?.('(prefers-color-scheme: dark)');

function saved(): ThemeChoice {
  try {
    const value = localStorage.getItem(KEY);
    return value === 'light' || value === 'dark' ? value : 'system';
  } catch {
    return 'system';
  }
}

function apply(choice: ThemeChoice) {
  const dark = choice === 'dark' || (choice === 'system' && !!systemDark()?.matches);
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
}

export function useTheme(): [ThemeChoice, (choice: ThemeChoice) => void] {
  const [choice, setChoice] = useState<ThemeChoice>(saved);

  useEffect(() => {
    apply(choice);
    try {
      if (choice === 'system') localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, choice);
    } catch {
      // Storage blocked (e.g. a private window): the choice still applies until the page reloads.
    }
    if (choice !== 'system') return;
    // Following the system: switch live when the system appearance changes.
    const query = systemDark();
    if (!query) return;
    const follow = () => apply('system');
    query.addEventListener('change', follow);
    return () => query.removeEventListener('change', follow);
  }, [choice]);

  return [choice, setChoice];
}
