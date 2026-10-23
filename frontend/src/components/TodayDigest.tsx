import type { Briefing, BriefingFixture, BriefingSource, EvidenceView } from '../types';
import { hrefFor } from '../route';
import SummaryText from './SummaryText';

interface Props {
  fixture: BriefingFixture;
  source: BriefingSource;
  onEvidence: (v: EvidenceView) => void;
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

// The Home page leads with the briefing summary above the chat box: every check in one short
// paragraph, each sentence with its sources, so nothing is ranked against things of another kind.
export default function TodayDigest({ fixture, source, onEvidence }: Props) {
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
      {briefing.summary ? (
        <SummaryText summary={briefing.summary} onEvidence={onEvidence} />
      ) : (
        <p className="headline">
          <strong>{briefing.at_risk.count} orders at risk</strong>
        </p>
      )}
      <a className="link" href={hrefFor({ page: 'briefing' })}>
        Full briefing · {briefing.decisions.length} flagged for review
      </a>
    </section>
  );
}
