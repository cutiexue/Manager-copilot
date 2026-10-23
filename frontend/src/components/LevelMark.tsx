import type { Level } from '../types';

export const LEVEL_LABEL: Record<Level, string> = { act: 'Act now', watch: 'Watch' };

// Status marks: a red circle for act now, an amber triangle for watch. Shape and colour both
// differ, so the two stay apart without colour vision, and the label always sits nearby.
// `title` is the hover text (the level's rule); the accessible name is the label alone.
export default function LevelMark({ level, title }: { level: Level; title?: string }) {
  const act = level === 'act';
  return (
    <svg className={`mark mark-${level}`} viewBox="0 0 20 20" width="18" height="18" role="img" aria-label={LEVEL_LABEL[level]}>
      <title>{title ?? LEVEL_LABEL[level]}</title>
      {act ? <circle className="mark-shape" cx="10" cy="10" r="9" /> : <path className="mark-shape" d="M10 2.2 18.4 17.4H1.6Z" />}
      <path className="mark-glyph" d={act ? 'M10 5.6v5.2' : 'M10 7.6v4.6'} />
      <circle className="mark-dot" cx="10" cy={act ? 14.2 : 15} r="1.2" />
    </svg>
  );
}
