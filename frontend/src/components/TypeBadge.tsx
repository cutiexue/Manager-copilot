import { FINDING_LABEL } from '../evidence';

// Text + symbol, never colour alone (plan §12.3).
const SYMBOL: Record<string, string> = {
  order_at_risk: '⚠',
  stage_output_drop: '▼',
  customer_slipping: '●',
};

export default function TypeBadge({ type }: { type: string }) {
  return (
    <span className={`badge badge-${type}`}>
      <span aria-hidden>{SYMBOL[type] ?? '•'}</span> {FINDING_LABEL[type] ?? type}
    </span>
  );
}
