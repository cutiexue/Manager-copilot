import type { Briefing, BriefingFixture, BriefingSource } from '../types';
import { hrefFor } from '../route';
import Headline from './Headline';

interface Props {
  fixture: BriefingFixture;
  source: BriefingSource;
}

/** Starter questions built from the briefing's own findings; templates only, no numbers. */
export function suggestionsFor(briefing: Briefing): string[] {
  const out: string[] = [];
  const order = briefing.findings.find((f) => f.type === 'order_at_risk');
  if (typeof order?.details.order_id === 'string') out.push(`Why is ${order.details.order_id} at risk?`);
  const drop = briefing.findings.find((f) => f.type === 'stage_output_drop');
  if (typeof drop?.details.stage === 'string') out.push(`How did ${drop.details.stage} do yesterday?`);
  out.push('Which orders are overdue?');
  return out;
}

// The briefing's headline above the chat box; the marked items are on the Briefing page.
export default function TodayDigest({ fixture, source }: Props) {
  const { briefing } = fixture;

  return (
    <section className="digest" aria-labelledby="digest-title">
      <div className="digest-head">
        <h2 id="digest-title">Today</h2>
        <span className="muted small">
          Data as of {briefing.as_of_date}
          {source === 'snapshot' ? ' · saved snapshot' : ''}
        </span>
      </div>
      <Headline briefing={briefing} />
      <a className="link" href={hrefFor({ page: 'briefing' })}>
        Full briefing
      </a>
    </section>
  );
}
