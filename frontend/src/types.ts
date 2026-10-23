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

/** One finding as a compact row; flagged = one of the briefing's review items. */
export interface CheckItem {
  key: string;
  name: string;
  context: string;
  /** Short reason, e.g. "16 days late" or "-29.3%" */
  tag: string;
  flagged: boolean;
  /** Suggested follow-up check for this kind of finding */
  note: string;
  finding: Finding;
}

/** Every finding of one check (finding type), with how the check picks them. */
export interface Check {
  type: FindingType;
  title: string;
  total: number;
  flagged: number;
  how_picked: string;
  /** When an item of this check gets a review flag */
  flag_rule: string;
  ranked_by: string | null;
  items: CheckItem[];
}

export interface Briefing {
  status: 'ok';
  as_of_date: string;
  snapshot_date: string;
  yesterday: {
    date: string;
    is_workday: boolean;
    message?: string;
    stages: YesterdayStage[];
  };
  at_risk: { count: number; orders: AtRiskOrder[]; source_rows: SourceRef[] };
  /** Missing from briefings produced before the summary existed */
  summary?: BriefingSummaryData;
  /** Missing from briefings produced before review flags existed */
  checks?: Check[];
  /** Flagged items across all checks */
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

export interface ChatMessage {
  role: 'human' | 'ai';
  content: string;
}

export interface SendMessageResponse {
  session_id: string;
  answer: string;
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
}

// ---- Locally proposed actions (no backend endpoint yet) ----
export type ActionState = 'PROPOSED' | 'CONFIRMED' | 'CANCELLED';

export interface ActionProposal {
  id: string;
  kind: 'reminder' | 'note';
  target: string;
  text: string;
  state: ActionState;
  created_at: string;
  decided_at?: string;
}
