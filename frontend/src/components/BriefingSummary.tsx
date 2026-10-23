import { useState, type ReactNode } from 'react';
import type {
  Briefing, BriefingFixture, BriefingSource, Check, CheckItem, CheckLevel, EvidenceView, Finding, Level,
} from '../types';
import { FINDING_LABEL, evidenceForFinding, findingFor, questionForFinding } from '../evidence';
import { longDate } from '../dates';
import type { ProposalDraft } from './ConfirmModal';
import Headline from './Headline';
import Icon from './Icon';
import LevelMark, { LEVEL_LABEL } from './LevelMark';
import YesterdayStrip from './YesterdayStrip';

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

/** Checks from the backend, or act-now-only ones for briefings produced before checks existed. */
function checksFor(briefing: Briefing): Check[] {
  if (briefing.checks) return briefing.checks;
  return (Object.keys(CHECK_TITLE) as (keyof typeof CHECK_TITLE)[]).map((type) => {
    const items = briefing.decisions
      .filter((d) => d.finding_type === type)
      .flatMap((d): CheckItem[] => {
        const finding = findingFor(briefing, d);
        return finding ? [{ key: d.about, name: d.about, context: '', tag: '', level: 'act', note: d.suggested_decision, finding }] : [];
      });
    return { type, title: CHECK_TITLE[type], total: items.length, how_picked: '', ranked_by: null, items };
  });
}

const levelOf = (item: CheckItem): Level => item.level ?? (item.flagged ? 'act' : 'watch');

/** A check's levels with their items. Briefings produced before levels existed only had `flagged`. */
function groupsFor(check: Check) {
  const levels: CheckLevel[] =
    check.levels ??
    (['act', 'watch'] as const).map((level) => ({
      level,
      label: LEVEL_LABEL[level],
      rule: level === 'act' ? (check.flag_rule ?? '') : '',
      count: 0,
    }));
  return levels
    .map((lv) => ({ ...lv, items: check.items.filter((item) => levelOf(item) === lv.level) }))
    .filter((group) => group.items.length > 0);
}

const tipFor = (check?: Check) =>
  check && [check.how_picked, check.ranked_by && `Ranked by ${check.ranked_by}.`].filter(Boolean).join(' ');

// Rows past this many in one level wait behind "Show all".
const GROUP_ROWS = 8;

interface CheckProps {
  check: Check;
  onEvidence: (v: EvidenceView) => void;
  onAsk: (text: string) => void;
  onRemind: (item: CheckItem) => void;
}

// One check's findings grouped by level. Each group opens with its mark, label and rule, so the
// rule behind every mark is on the page, and every row carries its group's mark.
function CheckRows({ check, onEvidence, onAsk, onRemind }: CheckProps) {
  const [expanded, setExpanded] = useState<Partial<Record<Level, boolean>>>({});
  const groups = groupsFor(check);
  if (groups.length === 0) return null;

  return (
    <table className="review">
      <caption className="sr-only">{check.title}</caption>
      {groups.map((group) => {
        const open = expanded[group.level] ?? false;
        const rows = open ? group.items : group.items.slice(0, GROUP_ROWS);
        const markTitle = group.rule ? `${group.label} · ${group.rule}` : group.label;
        return (
          <tbody key={group.level} className={`lvl-${group.level}`}>
            <tr className="lvl-head">
              <th scope="colgroup" colSpan={4}>
                <LevelMark level={group.level} title={markTitle} />
                <span className="lvl-label">{group.label}</span>
                {group.rule && <span className="lvl-rule">{group.rule}</span>}
              </th>
              <td className="lvl-count">{group.items.length}</td>
            </tr>
            {rows.map((item) => (
              <tr key={item.key}>
                <td className="mark-cell">
                  <LevelMark level={group.level} title={markTitle} />
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
            {group.items.length > GROUP_ROWS && (
              <tr className="lvl-more">
                <td colSpan={5}>
                  <button
                    className="link"
                    aria-expanded={open}
                    onClick={() => setExpanded((e) => ({ ...e, [group.level]: !open }))}
                  >
                    {open ? 'Show fewer' : `Show all ${group.items.length}`}
                  </button>
                </td>
              </tr>
            )}
          </tbody>
        );
      })}
    </table>
  );
}

function Section({ id, title, tip, children }: { id: string; title: string; tip?: string; children: ReactNode }) {
  return (
    <section className="check" aria-labelledby={id}>
      <div className="check-head">
        <h3 id={id} title={tip || undefined}>
          {title}
        </h3>
      </div>
      {children}
    </section>
  );
}

// The page reads like a daily production report: one headline, yesterday's output, then what to
// act on today, by check. Production comes first, as in the backend's own text briefing.
export default function BriefingSummary({ fixture, source, error, onRefresh, onEvidence, onAsk, onPropose }: Props) {
  const { briefing } = fixture;
  const checks = checksFor(briefing);
  const find = (type: Check['type']) => checks.find((c) => c.type === type);
  const production = find('stage_output_drop');
  const later = [find('order_at_risk'), find('customer_slipping')].filter((c): c is Check => !!c && c.items.length > 0);
  const rows = (check: Check) => (
    <CheckRows
      check={check}
      onEvidence={onEvidence}
      onAsk={onAsk}
      onRemind={(item) => onPropose(reminderFor(item.finding, item.note, briefing.as_of_date))}
    />
  );

  return (
    <section className="briefing" aria-labelledby="briefing-title">
      <div className="briefing-head">
        <div>
          <h2 id="briefing-title">Morning briefing</h2>
          <p className="dateline">{longDate(briefing.as_of_date)}</p>
        </div>
        {source === 'snapshot' && (
          <p className="notice small" role="status" title={error ?? undefined}>
            Live briefing unavailable, showing the saved snapshot.
            <button className="btn btn-small" onClick={onRefresh}>
              <Icon name="refresh" size={14} /> Retry
            </button>
          </p>
        )}
      </div>

      <Headline briefing={briefing} />

      <Section id="check-production" title="Production" tip={tipFor(production)}>
        <YesterdayStrip briefing={briefing} onEvidence={onEvidence} />
        {production && rows(production)}
      </Section>

      {later.map((check) => (
        <Section key={check.type} id={`check-${check.type}`} title={check.title} tip={tipFor(check)}>
          {rows(check)}
        </Section>
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
