// Shapes returned by the backend on the `src` branch (briefing.py, service.py, api.py).
// Keep these in sync with the backend; they mirror its output and add nothing.

export interface SourceRef {
  source: string;
  row: number;
  key: string;
}

export interface Evidence {
  source: string;
  source_rows: SourceRef[];
}

export interface BaselineRecord {
  date: string;
  stage: string;
  pieces_completed: number;
  source_row: number;
}

export interface YesterdayStage {
  stage: string;
  pieces_completed?: number;
  source_rows?: SourceRef[];
  output_status?: string;
  message?: string;
  baseline_workdays?: number;
  baseline_average?: number;
  change_percent?: number | null;
  baseline_records?: BaselineRecord[];
  comparison_status?: string;
}

export type FindingType = 'order_at_risk' | 'stage_output_drop' | 'customer_slipping';

export interface Finding {
  type: FindingType;
  severity: number;
  severity_basis: string;
  summary: string;
  details: Record<string, unknown>;
  evidence: Evidence;
}

export interface Decision {
  finding_type: FindingType;
  about: string;
  suggested_decision: string;
  evidence: Evidence;
}

export interface AtRiskOrder {
  order_id: string;
  customer: string;
  current_stage: string;
  risk_reasons: string[];
}

/** One sentence of the briefing summary, with the source rows behind it. */
export interface SummaryPoint {
  kind: string;
  text: string;
  evidence: Evidence | null;
  order_id?: string;
  stage?: string;
  customer?: string;
}

export interface BriefingSummaryData {
  text: string;
  points: SummaryPoint[];
}

/** How urgent a briefing item is: act on it now, or keep watching it. */
export type Level = 'act' | 'watch';

/** One level of a check, with the rule that puts items there. */
export interface CheckLevel {
  level: Level;
  label: string;
  /** e.g. "Late or idle 7+ days" */
  rule: string;
  count: number;
}

/** One finding as a compact row, at one level. */
export interface CheckItem {
  key: string;
  name: string;
  context: string;
  /** Short reason, e.g. "16 days late" or "−29.3%" */
  tag: string;
  /** Missing from briefings produced before levels existed; those set `flagged` instead */
  level?: Level;
  flagged?: boolean;
  /** Suggested follow-up check for this kind of finding */
  note: string;
  finding: Finding;
}

/** Every finding of one check (finding type), with how the check picks them. */
export interface Check {
  type: FindingType;
  title: string;
  total: number;
  how_picked: string;
  ranked_by: string | null;
  /** Missing from briefings produced before levels existed */
  levels?: CheckLevel[];
  /** Older briefings only: when an item was flagged */
  flag_rule?: string;
  items: CheckItem[];
}

export interface Briefing {
  status: 'ok';
  as_of_date: string;
  snapshot_date: string;
  /** The last workday before the briefing date (Saturday on a Monday) */
  yesterday: {
    date: string;
    /** "Yesterday" or "Last workday"; missing from briefings produced before 10/24 */
    label?: string;
    is_workday: boolean;
    message?: string;
    stages: YesterdayStage[];
  };
  at_risk: { count: number; orders: AtRiskOrder[]; source_rows: SourceRef[] };
  /** Missing from briefings produced before the summary existed */
  summary?: BriefingSummaryData;
  /** Missing from briefings produced before review flags existed */
  checks?: Check[];
  /** Items at each level across all checks */
  act_count?: number;
  watch_count?: number;
  /** Older briefings only: flagged items across all checks */
  review_count?: number;
  total_findings: number;
  findings: Finding[];
  decisions: Decision[];
  coverage_complete: boolean;
  data_gaps: { stage: string; section?: string; reason: string }[];
  comparison_windows: Record<string, string>;
  warnings: string[];
}

/** Same shape for the live `GET /briefings/latest` payload and the saved snapshot fixture. */
export interface BriefingFixture {
  generated_at: string;
  generator: string;
  backend_commit: string | null;
  briefing: Briefing;
  /** "<source>#<row>" -> the raw CSV row, keyed by column name */
  source_rows: Record<string, Record<string, string>>;
  briefing_text: string;
}

/** Where the briefing on screen came from. */
export type BriefingSource = 'checking' | 'live' | 'snapshot';

// ---- Chat API (api.py) ----
export interface Session {
  id: string;
  title: string;
  created_at?: string;
  updated_at?: string;
  /** false for a conversation that was created but never got a message */
  has_messages?: boolean;
}

/** One tool the agent called in a turn, with the status its result reported */
export interface ToolCall {
  name: string;
  arguments: Record<string, unknown>;
  status: string | null;
}

/** The CSV rows the turn's tools cited, and those rows as they appear in the files */
export interface TurnEvidence {
  refs: SourceRef[];
  rows: Record<string, Record<string, string>>;
}

export interface ChatMessage {
  role: 'human' | 'ai';
  content: string;
  /** On answers that used tools */
  tool_calls?: ToolCall[];
  evidence?: TurnEvidence;
  proposals?: Proposal[];
}

export interface SendMessageResponse {
  session_id: string;
  answer: string;
  tool_calls: ToolCall[];
  evidence: TurnEvidence;
  proposals: Proposal[];
  prompt_version: string;
}

// ---- Follow-ups (actions.py): proposals and what confirming them creates ----
export type ProposalKind = 'reminder' | 'note' | 'chase_message' | 'watch';
export type ProposalStatus = 'PROPOSED' | 'EXECUTED' | 'CANCELLED' | 'FAILED' | 'EXPIRED';

export interface Proposal {
  id: string;
  kind: ProposalKind;
  status: ProposalStatus;
  source: 'chat' | 'ui';
  session_id: string | null;
  payload: Record<string, unknown>;
  summary: string;
  reason: string | null;
  created_at: string;
  expires_at: string;
  decided_at: string | null;
  result_kind: string | null;
  result_id: string | null;
  error: string | null;
}

export interface ConfirmResult {
  proposal: Proposal;
  result: Record<string, unknown> | null;
  /** true when it had already been confirmed: nothing new was created */
  already_done: boolean;
}

export interface Reminder {
  id: string;
  proposal_id: string;
  order_id: string | null;
  subject: string | null;
  text: string;
  remind_at: string;
  status: 'SCHEDULED' | 'DUE' | 'DISMISSED';
  created_at: string;
  due_at: string | null;
}

export interface OrderNote {
  id: string;
  order_id: string;
  text: string;
  created_at: string;
}

export interface ChaseDraft {
  id: string;
  order_id: string;
  customer: string;
  text: string;
  created_at: string;
}

export type WatchCondition = 'not_moved_by' | 'becomes_overdue' | 'completed' | 'reaches_stage';

export interface Watch {
  id: string;
  order_id: string;
  condition: WatchCondition;
  deadline: string | null;
  stage: string | null;
  status: 'ACTIVE' | 'PAUSED' | 'TRIGGERED' | 'RESOLVED' | 'CANCELLED';
  summary: string;
  baseline: Record<string, string>;
  created_at: string;
  last_checked_at: string | null;
  last_result: string | null;
  outcome: string | null;
}

export interface Alert {
  id: string;
  kind: 'watch' | 'reminder' | 'briefing';
  ref_id: string | null;
  title: string;
  body: string | null;
  created_at: string;
  read_at: string | null;
}

export interface AuditEvent {
  id: number;
  at: string;
  actor: 'agent' | 'user' | 'system' | 'scheduler';
  event: string;
  proposal_id: string | null;
  target_kind: string | null;
  target_id: string | null;
  detail: Record<string, unknown> | null;
}

export interface FollowUpCounts {
  pending_proposals: number;
  due_reminders: number;
  active_watches: number;
  unread_alerts: number;
}

/** A scripted data snapshot that watches are checked against */
export interface DataSnapshot {
  version: string;
  date: string;
  label: string;
}

export interface SnapshotState {
  current: DataSnapshot;
  next: DataSnapshot | null;
  versions: DataSnapshot[];
}

// ---- Order search (GET /orders/search) ----
export interface OrderHit {
  order_id: string;
  customer: string;
  product: string;
  category: string;
  pieces: number;
  due_date: string;
  status: 'IN_PROGRESS' | 'COMPLETE';
  current_stage: string;
  last_activity_date: string;
  /** From the backend's risk rules; empty when the order needs no attention */
  risk_reasons: string[];
  source_row: number;
}

export interface OrderSearchResult {
  status: 'ok';
  query: string;
  /** All matches; only the first `count` are returned */
  total: number;
  count: number;
  orders: OrderHit[];
  snapshot_date: string;
}

// ---- What the evidence drawer shows ----
export interface EvidenceView {
  title: string;
  /** Plain-language statement of the claim, copied from the tool output */
  claim: string;
  /** Calculation lines, copied from tool output fields (never computed here) */
  calculation: { label: string; value: string }[];
  refs: SourceRef[];
  /** Raw rows for these refs when they did not come with the briefing (e.g. a chat answer) */
  rows?: Record<string, Record<string, string>>;
}
