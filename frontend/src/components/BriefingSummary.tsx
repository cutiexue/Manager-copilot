import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { flushSync } from 'react-dom';
import { useGlassPointer, useRollingNumber, withViewTransition } from '../motion';
import type {
  Briefing, BriefingFixture, BriefingSource, Check, CheckItem, CheckLevel, EvidenceView, Finding, Level,
} from '../types';
import { FINDING_LABEL, evidenceForFinding, findingFor, questionForFinding } from '../evidence';
import { longDate } from '../dates';
import type { ProposalDraft } from './ConfirmModal';
import Headline from './Headline';
import Icon from './Icon';
import LevelMark, { LEVEL_LABEL } from './LevelMark';
import Narrative from './Narrative';
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
                  <button className="row-btn" aria-label={`Evidence for ${item.name}`} onClick={() => onEvidence(evidenceForFinding(item.finding))}>
                    <Icon name="evidence" size={15} />
                    <span className="row-btn-label">Evidence</span>
                  </button>
                  <button className="row-btn" aria-label={`Ask about ${item.name}`} onClick={() => onAsk(questionForFinding(item.finding))}>
                    <Icon name="ask" size={15} />
                    <span className="row-btn-label">Ask</span>
                  </button>
                  <button className="row-btn" aria-label={`Remind about ${item.name}`} onClick={() => onRemind(item)}>
                    <Icon name="remind" size={15} />
                    <span className="row-btn-label">Remind</span>
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

type ModuleId = Check['type'];

const MODULE_ORDER: ModuleId[] = ['stage_output_drop', 'order_at_risk', 'customer_slipping'];
const vt = (id: ModuleId) => ({ viewTransitionName: `module-${id}` }) as CSSProperties;

// Counts come from the backend's levels when it sends them; older briefings are counted from their items.
function levelCounts(check?: Check) {
  const fromBackend = (level: Level) => check?.levels?.find((l) => l.level === level)?.count;
  const items = check?.items ?? [];
  if (check?.levels) return { act: fromBackend('act') ?? 0, watch: fromBackend('watch') ?? 0 };
  return { act: items.filter((i) => levelOf(i) === 'act').length, watch: items.filter((i) => levelOf(i) === 'watch').length };
}

function CountLine({ check }: { check?: Check }) {
  const c = levelCounts(check);
  const unchecked = check?.not_checked?.length ?? 0;
  if (c.act + c.watch === 0) {
    // A check that could not run is never shown as all clear.
    return <span className="module-quiet">{unchecked > 0 ? `${unchecked} not checked` : 'Nothing to flag'}</span>;
  }
  return (
    <span className="module-levels">
      {c.act > 0 && (
        <span>
          <LevelMark level="act" /> {c.act} act now
        </span>
      )}
      {c.watch > 0 && (
        <span>
          <LevelMark level="watch" /> {c.watch} watch
        </span>
      )}
      {unchecked > 0 && <span className="module-quiet">{unchecked} not checked</span>}
    </span>
  );
}

/** "knitting, assembly · Missing production records …" for a check that could not judge everything. */
function notCheckedText(check?: Check): string | null {
  const gaps = check?.not_checked ?? [];
  if (gaps.length === 0) return null;
  const reasons = [...new Set(gaps.map((g) => g.reason))].join(' ');
  return `Not checked · ${gaps.map((g) => g.stage.toLowerCase()).join(', ')} · ${reasons}`;
}

/** The figure on a card or thumbnail: a dash when the check found nothing because it could not run. */
function checkFigure(check?: Check): number | null {
  const total = check?.total ?? check?.items.length ?? 0;
  return total === 0 && (check?.not_checked?.length ?? 0) > 0 ? null : total;
}

// A module in the overview: its title, how many items it flags and a preview. Clicking it opens
// the module in place.
function ModuleCard({ id, title, check, briefing, onOpen }: {
  id: ModuleId; title: string; check?: Check; briefing: Briefing; onOpen: () => void;
}) {
  const ref = useRef<HTMLButtonElement>(null);
  useGlassPointer(ref);
  const y = briefing.yesterday;
  const figure = checkFigure(check);
  const total = useRollingNumber(figure ?? 0);
  return (
    <button ref={ref} className="module glass-card" style={vt(id)} onClick={onOpen} aria-label={`Open ${title}`}>
      <span className="module-head">
        <span className="module-title">{title}</span>
        <span className="module-open-hint">Open</span>
      </span>
      <span className="module-figure">{figure === null ? '—' : Math.round(total)}</span>
      <CountLine check={check} />
      {id === 'stage_output_drop' && y.is_workday ? (
        <span className="module-stages">
          {y.stages.map((st) => (
            <span key={st.stage} className="module-stage">
              <span className="module-stage-name">{st.stage.toLowerCase()}</span>
              <span className="module-stage-value">{st.pieces_completed?.toLocaleString('en-US') ?? '—'}</span>
            </span>
          ))}
        </span>
      ) : (
        <span className="module-preview">
          {(check?.items ?? []).slice(0, 3).map((item) => (
            <span key={item.key} className="module-preview-row">
              <span className="module-preview-name">{item.name}</span>
              <span className="module-preview-tag">{item.tag}</span>
            </span>
          ))}
        </span>
      )}
    </button>
  );
}

// The page reads like a daily production report: the headline and three sentences on one dark card,
// then one module per check. A module opens in place; the others wait as thumbnails below it.
export default function BriefingSummary({ fixture, source, error, onRefresh, onEvidence, onAsk, onPropose }: Props) {
  const { briefing } = fixture;
  const [open, setOpen] = useState<ModuleId | null>(null);
  const checks = checksFor(briefing);
  const find = (type: ModuleId) => checks.find((c) => c.type === type);
  const titleOf = (type: ModuleId) => find(type)?.title ?? CHECK_TITLE[type];
  const rows = (check: Check) => (
    <CheckRows
      check={check}
      onEvidence={onEvidence}
      onAsk={onAsk}
      onRemind={(item) => onPropose(reminderFor(item.finding, item.note, briefing.as_of_date))}
    />
  );
  const show = (id: ModuleId | null) => withViewTransition(() => flushSync(() => setOpen(id)));

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') show(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  const openCheck = open ? find(open) : undefined;

  return (
    <section className="briefing" aria-labelledby="briefing-title">
      <header className="page-head briefing-head">
        <div>
          <h1 id="briefing-title">Morning briefing</h1>
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
      </header>

      <div className="hero-card">
        <Headline briefing={briefing} />
        <Narrative briefing={briefing} onEvidence={onEvidence} />
      </div>

      {open === null ? (
        <div className="modules">
          {MODULE_ORDER.map((id) => (
            <ModuleCard key={id} id={id} title={titleOf(id)} check={find(id)} briefing={briefing} onOpen={() => show(id)} />
          ))}
        </div>
      ) : (
        <>
          <section className="module-detail glass-panel" style={vt(open)} aria-labelledby={`check-${open}`}>
            <div className="module-detail-head">
              <div>
                <h2 id={`check-${open}`} title={tipFor(openCheck) || undefined}>
                  {titleOf(open)}
                </h2>
                <CountLine check={openCheck} />
              </div>
              <button className="btn" onClick={() => show(null)}>
                Close
              </button>
            </div>
            {open === 'stage_output_drop' && <YesterdayStrip briefing={briefing} onEvidence={onEvidence} />}
            {openCheck && openCheck.items.length > 0 ? (
              <>
                <div className="rank-card">{rows(openCheck)}</div>
                {notCheckedText(openCheck) && <p className="empty small">{notCheckedText(openCheck)}</p>}
              </>
            ) : (
              <p className="empty">{notCheckedText(openCheck) ?? 'Nothing flagged in this check today.'}</p>
            )}
          </section>
          <nav className="module-thumbs" aria-label="Other checks">
            {MODULE_ORDER.filter((id) => id !== open).map((id) => (
              <button key={id} className="module-thumb" style={vt(id)} onClick={() => show(id)}>
                <span className="module-thumb-title">{titleOf(id)}</span>
                <span className="module-thumb-count">{checkFigure(find(id)) ?? '—'}</span>
              </button>
            ))}
          </nav>
        </>
      )}

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
