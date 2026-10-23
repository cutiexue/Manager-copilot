import { useState } from 'react';
import type { Briefing, BriefingFixture, BriefingSource, Check, CheckItem, EvidenceView, Finding } from '../types';
import { FINDING_LABEL, evidenceForFinding, findingFor, questionForFinding } from '../evidence';
import type { ProposalDraft } from './ConfirmModal';
import Icon from './Icon';

interface Props {
  fixture: BriefingFixture;
  source: BriefingSource;
  error: string | null;
  onRefresh: () => void;
  onEvidence: (v: EvidenceView) => void;
  onAsk: (text: string) => void;
  onPropose: (d: ProposalDraft) => void;
}

/** Reminder draft for a finding: about its order, or about the customer or stage it names. */
function reminderFor(finding: Finding, note: string, asOfDate: string): ProposalDraft {
  const field = (key: string) => (typeof finding.details[key] === 'string' ? (finding.details[key] as string) : undefined);
  const orderId = field('order_id');
  const about = orderId
    ? {
        order: {
          order_id: orderId,
          customer: field('customer') ?? '',
          detail: [field('current_stage'), field('due_date') && `due ${field('due_date')}`].filter(Boolean).join(' · '),
        },
      }
    : {
        subject: field('customer') ? `${field('customer')} (customer)` : field('stage') ? `${field('stage')} stage` : finding.summary,
      };
  return {
    kind: 'reminder',
    ...about,
    text: `Follow up: ${finding.summary} ${note}`,
    reason: `${FINDING_LABEL[finding.type]} in the ${asOfDate} briefing`,
  };
}

const CHECK_TITLE = { order_at_risk: 'Orders at risk', stage_output_drop: 'Production', customer_slipping: 'Customers' };

/** Checks from the backend, or flagged-only ones for briefings produced before checks existed. */
function checksFor(briefing: Briefing): Check[] {
  if (briefing.checks) return briefing.checks;
  return (Object.keys(CHECK_TITLE) as (keyof typeof CHECK_TITLE)[]).map((type) => {
    const items = briefing.decisions
      .filter((d) => d.finding_type === type)
      .flatMap((d) => {
        const finding = findingFor(briefing, d);
        return finding
          ? [{ key: d.about, name: d.about, context: '', tag: '', flagged: true, note: d.suggested_decision, finding }]
          : [];
      });
    return {
      type, title: CHECK_TITLE[type], total: items.length, flagged: items.length, how_picked: '', flag_rule: '', ranked_by: null, items,
    };
  });
}

// Unflagged rows shown under the flagged ones before "Show all".
const EXTRA_ROWS = 2;

interface CheckProps {
  check: Check;
  onEvidence: (v: EvidenceView) => void;
  onAsk: (text: string) => void;
  onRemind: (item: CheckItem) => void;
}

// Every finding of one check as a compact row. The briefing's review items carry a flag and come
// first; how the check picks its findings is in the heading's tooltip rather than on the page.
function CheckTable({ check, onEvidence, onAsk, onRemind }: CheckProps) {
  const [expanded, setExpanded] = useState(false);
  const rest = check.items.filter((item) => !item.flagged);
  const visible = expanded ? check.items : [...check.items.filter((item) => item.flagged), ...rest.slice(0, EXTRA_ROWS)];
  const rule = [check.how_picked, check.ranked_by && `Ranked by ${check.ranked_by}.`].filter(Boolean).join(' ');

  return (
    <section className="check" aria-labelledby={`check-${check.type}`}>
      <div className="check-head">
        <h3 id={`check-${check.type}`} title={rule || undefined}>
          {check.title}
        </h3>
        <span className="check-count">{check.total}</span>
        {check.flagged > 0 && (
          <span className="check-flagged" title={check.flag_rule || undefined}>
            <span className="flag-dot" aria-hidden /> {check.flagged} flagged for review
          </span>
        )}
      </div>
      <table className="review">
        {rule && <caption className="sr-only">{`${check.title}: ${rule}`}</caption>}
        <tbody>
          {visible.map((item) => (
            <tr key={item.key} className={item.flagged ? 'is-flagged' : undefined}>
              <td className="flag-cell">
                {item.flagged && (
                  <span className="flag" role="img" aria-label="Flagged for review" title={check.flag_rule || 'Flagged for review'}>
                    !
                  </span>
                )}
              </td>
              <th scope="row" className="row-name">
                {item.name}
              </th>
              <td className="row-context">{item.context}</td>
              <td className="row-tag">{item.tag}</td>
              <td className="row-icons">
                <button
                  className="icon-btn"
                  title="Evidence"
                  aria-label={`Evidence for ${item.name}`}
                  onClick={() => onEvidence(evidenceForFinding(item.finding))}
                >
                  <Icon name="evidence" />
                </button>
                <button
                  className="icon-btn"
                  title="Ask Co-Pilot"
                  aria-label={`Ask about ${item.name}`}
                  onClick={() => onAsk(questionForFinding(item.finding))}
                >
                  <Icon name="ask" />
                </button>
                <button className="icon-btn" title="Remind…" aria-label={`Remind about ${item.name}`} onClick={() => onRemind(item)}>
                  <Icon name="remind" />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {rest.length > EXTRA_ROWS && (
        <button className="link" onClick={() => setExpanded((e) => !e)} aria-expanded={expanded}>
          {expanded ? 'Show fewer' : `Show all ${check.total}`}
        </button>
      )}
    </section>
  );
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

      <p className="headline">
        <strong>{briefing.at_risk.count} orders at risk</strong> · {briefing.review_count ?? briefing.decisions.length} flagged
        for review
      </p>

      {checksFor(briefing)
        .filter((check) => check.items.length > 0)
        .map((check) => (
          <CheckTable
            key={check.type}
            check={check}
            onEvidence={onEvidence}
            onAsk={onAsk}
            onRemind={(item) => onPropose(reminderFor(item.finding, item.note, briefing.as_of_date))}
          />
        ))}

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
