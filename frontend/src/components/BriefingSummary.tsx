import type { Briefing, BriefingFixture, BriefingSource, Decision, EvidenceView, SummarySection } from '../types';
import { FINDING_LABEL, evidenceForDecision, findingFor, questionFor } from '../evidence';
import { hrefFor } from '../route';
import type { ProposalDraft } from './ConfirmModal';
import Icon from './Icon';
import SummaryText from './SummaryText';

interface Props {
  fixture: BriefingFixture;
  source: BriefingSource;
  error: string | null;
  onRefresh: () => void;
  onEvidence: (v: EvidenceView) => void;
  onAsk: (text: string) => void;
  onPropose: (d: ProposalDraft) => void;
}

/** Reminder draft for a briefing item: about its order, or about the customer or stage it names. */
function reminderFor(briefing: Briefing, d: Decision): ProposalDraft {
  const details = findingFor(briefing, d)?.details ?? {};
  const field = (key: string) => (typeof details[key] === 'string' ? (details[key] as string) : undefined);
  const orderId = field('order_id');
  const about = orderId
    ? {
        order: {
          order_id: orderId,
          customer: field('customer') ?? '',
          detail: [field('current_stage'), field('due_date') && `due ${field('due_date')}`].filter(Boolean).join(' · '),
        },
      }
    : { subject: field('customer') ? `${field('customer')} (customer)` : field('stage') ? `${field('stage')} stage` : d.about };
  return {
    kind: 'reminder',
    ...about,
    text: `Follow up: ${d.about} ${d.suggested_decision}`,
    reason: `${FINDING_LABEL[d.finding_type]} in the ${briefing.as_of_date} briefing`,
  };
}

const SECTION_TITLE = { order_at_risk: 'Orders at risk', stage_output_drop: 'Production', customer_slipping: 'Customers' };

/** Sections from the backend, or plain ones for briefings produced before the summary existed. */
function sectionsFor(briefing: Briefing): SummarySection[] {
  if (briefing.summary) return briefing.summary.sections;
  return (['order_at_risk', 'stage_output_drop', 'customer_slipping'] as const).map((type) => ({
    type,
    title: SECTION_TITLE[type],
    total: type === 'order_at_risk' ? briefing.at_risk.count : briefing.decisions.filter((d) => d.finding_type === type).length,
    how_picked: '',
    ranked_by: null,
  }));
}

export default function BriefingSummary({ fixture, source, error, onRefresh, onEvidence, onAsk, onPropose }: Props) {
  const { briefing } = fixture;

  return (
    <section className="briefing" aria-labelledby="briefing-title">
      <div className="briefing-head">
        <h2 id="briefing-title">Morning briefing · {briefing.as_of_date}</h2>
        {source === 'snapshot' && (
          <p className="notice small" role="status" title={error ?? undefined}>
            Live briefing unavailable, showing the saved snapshot.
            <button className="btn btn-small" onClick={onRefresh}>
              <Icon name="refresh" size={14} /> Retry
            </button>
          </p>
        )}
      </div>

      {briefing.summary ? (
        <SummaryText summary={briefing.summary} onEvidence={onEvidence} />
      ) : (
        <p className="headline">
          <strong>{briefing.at_risk.count} orders at risk</strong>
        </p>
      )}
      {/* The backend calls these "decisions"; each is a suggested follow-up check, not a decision the system made. */}
      <p className="followups">
        <strong>{briefing.decisions.length} items to follow up</strong>, grouped by the check that found them. Each has a
        suggested next step.
      </p>

      {sectionsFor(briefing).map((section) => {
        const items = briefing.decisions.filter((d) => d.finding_type === section.type);
        if (items.length === 0) return null;
        return (
          <section key={section.type} className="check" aria-labelledby={`check-${section.type}`}>
            <div className="check-head">
              <h3 id={`check-${section.type}`}>{section.title}</h3>
              <span className="check-count">
                {items.length < section.total ? `top ${items.length} of ${section.total}` : section.total}
              </span>
              {section.type === 'order_at_risk' && items.length < section.total && (
                <a className="link" href={hrefFor({ page: 'orders' })}>
                  All {section.total} at-risk orders
                </a>
              )}
            </div>
            {section.how_picked && (
              <p className="check-rule">
                {section.how_picked}
                {section.ranked_by && items.length > 1 && <> Highest first, by {section.ranked_by}.</>}
              </p>
            )}
            <ul className="items">
              {items.map((d) => (
                <li key={d.about} className="item">
                  <p className="item-title">{d.about}</p>
                  <p className="item-note">
                    <span className="item-note-label">Next step:</span> {d.suggested_decision}
                  </p>
                  <div className="row-actions">
                    <button className="btn btn-ghost btn-small" onClick={() => onEvidence(evidenceForDecision(briefing, d))}>
                      <Icon name="evidence" size={14} /> Evidence
                    </button>
                    <button className="btn btn-ghost btn-small" onClick={() => onAsk(questionFor(briefing, d))}>
                      <Icon name="ask" size={14} /> Ask
                    </button>
                    <button className="btn btn-ghost btn-small" onClick={() => onPropose(reminderFor(briefing, d))}>
                      <Icon name="remind" size={14} /> Remind…
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        );
      })}

      {briefing.warnings.length > 0 && (
        <ul className="warnings small">
          {briefing.warnings.map((w) => (
            <li key={w}>ⓘ {w}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
