import type { BriefingSource } from '../types';
import { hrefFor } from '../route';
import Icon from './Icon';
import ThemeSwitch from './ThemeSwitch';
import type { ThemeChoice } from '../theme';

// The real date, for the reminders pill: reminders run on the real calendar, business data on the dataset date.
const REAL_TODAY = new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'Asia/Singapore' });

interface Props {
  asOfDate: string;
  briefingSource: BriefingSource;
  /** Where the briefing came from (generator, time, backend commit), shown on hover */
  briefingDetail: string;
  onSearch: () => void;
  theme: ThemeChoice;
  setTheme: (c: ThemeChoice) => void;
}

const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform);

// The thin bar above every page: who this is for, which day the data describes, and search.
export default function TopBar({ asOfDate, briefingSource, briefingDetail, onSearch, theme, setTheme }: Props) {
  return (
    <header className="topbar">
      <a className="brand" href={hrefFor({ page: 'home' })}>
        <span className="logo" aria-hidden />
        <span>
          <span className="brand-name">Manager Co-Pilot</span>
          <span className="brand-sub">SweaterCo · General Manager</span>
        </span>
      </a>
      <div className="topbar-right">
        <span className="pill pill-data" title="Orders, output and the briefing are judged on the dataset date.">
          <span className="phone-sr">Data as of </span>{asOfDate}
        </span>
        <span className="pill pill-soft hide-narrow" title="Reminders fire on the real calendar, Singapore time.">
          Reminders: real time, {REAL_TODAY}
        </span>
        {briefingSource !== 'live' && (
          <span className="pill pill-warn" title={briefingDetail}>
            {briefingSource === 'checking' ? 'Briefing: checking…' : 'Briefing: snapshot'}
          </span>
        )}
        <button className="search-btn" onClick={onSearch} aria-label="Search pages and conversations" aria-keyshortcuts="Control+K">
          <Icon name="search" size={15} />
          <span className="hide-narrow">Search</span>
          <kbd className="hide-narrow">{isMac ? '⌘' : 'Ctrl'} K</kbd>
        </button>
        <ThemeSwitch choice={theme} setChoice={setTheme} />
      </div>
    </header>
  );
}
