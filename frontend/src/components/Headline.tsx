import type { Briefing } from '../types';
import LevelMark from './LevelMark';

/** Items to act on now across all checks; older briefings counted flags or decisions instead. */
export function actCount(briefing: Briefing): number {
  return briefing.act_count ?? briefing.review_count ?? briefing.decisions.length;
}

// The one line that opens the briefing, here and on Home: orders at risk, and how many items
// across the checks need action now (the red marks on the Briefing page).
export default function Headline({ briefing }: { briefing: Briefing }) {
  return (
    <p className="headline">
      <strong>{briefing.at_risk.count} orders at risk</strong> · <LevelMark level="act" /> {actCount(briefing)} to act
      on now
    </p>
  );
}
