// Turn tool outputs into what the evidence drawer shows.
// Rule from the implementation plan: the frontend never computes business numbers.
// Every value below is copied (and only formatted) from fields the backend returned.
import type { AtRiskOrder, Briefing, Decision, Finding, SourceRef, YesterdayStage } from './types';

const PRODUCTION = 'track1/data/production_log.csv';

const LABELS: Record<string, string> = {
  order_id: 'Order',
  customer: 'Customer',
  current_stage: 'Current stage',
  due_date: 'Due date',
  last_activity_date: 'Last activity',
  overdue_calendar_days: 'Overdue (calendar days)',
  idle_calendar_days: 'Idle (calendar days)',
  risk_reasons: 'Risk reasons',
  stage: 'Stage',
  recent_workdays: 'Recent window (workdays)',
  baseline_workdays: 'Baseline window (workdays)',
  recent_mean: 'Recent mean (pcs/workday)',
  baseline_mean: 'Baseline mean (pcs/workday)',
  change_percent: 'Change (%)',
  order_ids: 'Orders',
};

const fmt = (v: unknown): string =>
  Array.isArray(v) ? v.join(', ') : v === null || v === undefined ? '—' : String(v);

export const FINDING_LABEL: Record<string, string> = {
  order_at_risk: 'Order at risk',
  stage_output_drop: 'Output drop',
  customer_slipping: 'Customer slipping',
};

export function findingFor(briefing: Briefing, decision: Decision): Finding | undefined {
  return briefing.findings.find((f) => f.summary === decision.about && f.type === decision.finding_type);
}

/** The question an "Ask" button puts into the chat box for a finding. */
export function questionForFinding(finding: Finding): string {
  const orderId = finding.details.order_id;
  return typeof orderId === 'string' ? `What is the latest status of ${orderId}?` : `Tell me more about: ${finding.summary}`;
}

export function evidenceForFinding(finding: Finding) {
  return {
    title: FINDING_LABEL[finding.type] ?? finding.type,
    claim: finding.summary,
    calculation: [
      ...Object.entries(finding.details).map(([k, v]) => ({ label: LABELS[k] ?? k, value: fmt(v) })),
      { label: 'Ranking score', value: `${finding.severity} (${finding.severity_basis})` },
    ],
    refs: finding.evidence.source_rows,
  };
}

export function evidenceForStage(date: string, s: YesterdayStage) {
  const baselineRefs: SourceRef[] = (s.baseline_records ?? []).map((r) => ({
    source: PRODUCTION,
    row: r.source_row,
    key: `${r.date} ${r.stage}`,
  }));
  return {
    title: `${s.stage} output on ${date}`,
    claim:
      s.pieces_completed !== undefined
        ? `${s.stage} completed ${s.pieces_completed} pieces on ${date}.`
        : `${s.stage}: ${s.output_status ?? 'no data'}${s.message ? ` — ${s.message}` : ''}`,
    calculation: [
      { label: 'Pieces completed', value: fmt(s.pieces_completed) },
      { label: 'Baseline average', value: s.baseline_average !== undefined ? s.baseline_average.toFixed(1) : '—' },
      { label: 'Baseline window (workdays)', value: fmt(s.baseline_workdays) },
      { label: 'Change vs baseline (%)', value: s.change_percent != null ? s.change_percent.toFixed(2) : '—' },
    ],
    refs: [...(s.source_rows ?? []), ...baselineRefs],
  };
}

export function evidenceForOrder(briefing: Briefing, o: AtRiskOrder) {
  return {
    title: `${o.order_id} at risk`,
    claim: `${o.order_id} (${o.customer}, stage ${o.current_stage}): ${o.risk_reasons.join('; ')}.`,
    calculation: [
      { label: 'Risk reasons', value: o.risk_reasons.join('; ') },
      { label: 'As-of date', value: briefing.as_of_date },
    ],
    refs: briefing.at_risk.source_rows.filter((r) => r.key === o.order_id),
  };
}
