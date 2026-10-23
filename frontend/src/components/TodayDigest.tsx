import type { Briefing, BriefingFixture, BriefingSource, EvidenceView } from '../types';
import { evidenceForDecision, questionFor } from '../evidence';
import { hrefFor } from '../route';
import TypeBadge from './TypeBadge';

interface Props {
  fixture: BriefingFixture;
  source: BriefingSource;
  onEvidence: (v: EvidenceView) => void;
  onAsk: (text: string) => void;
}

const TOP = 3;

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

// The Home page shows the top of the morning briefing above the chat box, so the most
// important risks are visible on arrival without leaving the conversation.
export default function TodayDigest({ fixture, source, onEvidence, onAsk }: Props) {
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
      <p className="digest-headline">
        <strong>{briefing.at_risk.count} orders at risk</strong> · {briefing.decisions.length} items need your decision
      </p>
      <ol className="digest-list">
        {briefing.decisions.slice(0, TOP).map((d, i) => (
          <li key={d.about}>
            <span className="rank" aria-label={`Priority ${i + 1}`}>{i + 1}</span>
            <div className="digest-item">
              <TypeBadge type={d.finding_type} />
              <p>{d.about}</p>
            </div>
            <div className="row-actions">
              <button className="btn btn-small" onClick={() => onEvidence(evidenceForDecision(briefing, d))}>
                Evidence
              </button>
              <button className="btn btn-small" onClick={() => onAsk(questionFor(briefing, d))}>
                Ask
              </button>
            </div>
          </li>
        ))}
      </ol>
      <a className="link" href={hrefFor({ page: 'briefing' })}>
        Full briefing
      </a>
    </section>
  );
}
