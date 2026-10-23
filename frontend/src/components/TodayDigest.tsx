import type { Briefing, BriefingFixture, BriefingSource } from '../types';
import { hrefFor } from '../route';

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

// One line of today's numbers above the chat box; the flagged details are on the Briefing page.
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
      <p className="headline">
        <strong>{briefing.at_risk.count} orders at risk</strong> · {briefing.review_count ?? briefing.decisions.length} flagged
        for review
      </p>
      <a className="link" href={hrefFor({ page: 'briefing' })}>
        Full briefing
      </a>
    </section>
  );
}
