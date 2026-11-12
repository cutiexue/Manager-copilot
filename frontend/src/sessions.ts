import type { Session } from './types';

// Conversation times are real (wall-clock) times, unlike the data dates in dates.ts.

const DAY = 86_400_000;

/** When a conversation last changed, in ms. SQLite stores UTC as "2026-11-12 01:03:27" with no zone,
 *  which Date.parse would read as local time; such values are read as UTC here. */
export function sessionTime(s: Session): number {
  const raw = s.updated_at ?? s.created_at;
  if (!raw) return Date.now(); // just created in this tab; the next list load brings its time
  const iso = /^\d{4}-\d\d-\d\d \d\d:\d\d(:\d\d)?$/.test(raw) ? `${raw.replace(' ', 'T')}Z` : raw;
  return Date.parse(iso);
}

/** Today, Previous 7 days or Older, by when the conversation last changed. */
export function sessionGroup(s: Session, now: number): string {
  const at = sessionTime(s);
  if (Number.isNaN(at)) return 'Older';
  if (new Date(at).toDateString() === new Date(now).toDateString()) return 'Today';
  return now - at < 7 * DAY ? 'Previous 7 days' : 'Older';
}

/** "9:03 AM" for today, "12 Nov" before that. */
export function sessionWhen(s: Session, now: number): string {
  const at = sessionTime(s);
  if (Number.isNaN(at)) return '';
  const d = new Date(at);
  return d.toDateString() === new Date(now).toDateString()
    ? d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
    : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
}

/** Conversations with at least one message whose title contains every word of the filter. */
export function matchingSessions(sessions: Session[], filter: string): Session[] {
  const words = filter.trim().toLowerCase().split(/\s+/).filter(Boolean);
  return sessions
    .filter((s) => s.has_messages !== false)
    .filter((s) => words.every((w) => s.title.toLowerCase().includes(w)));
}
