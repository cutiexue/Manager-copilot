import type { BriefingSummaryData, EvidenceView } from '../types';
import { evidenceForPoint } from '../evidence';
import Icon from './Icon';

interface Props {
  summary: BriefingSummaryData;
  onEvidence: (v: EvidenceView) => void;
}

// The backend writes the summary one sentence per check; each sentence keeps a small
// citation button that opens the source rows behind it.
export default function SummaryText({ summary, onEvidence }: Props) {
  return (
    <p className="summary">
      {summary.points.map((point, i) => (
        <span key={i}>
          {point.text}
          {point.evidence && (
            <button
              className="cite"
              onClick={() => onEvidence(evidenceForPoint(point))}
              aria-label={`Source rows for: ${point.text}`}
              title="Show source rows"
            >
              <Icon name="evidence" size={13} />
            </button>
          )}{' '}
        </span>
      ))}
    </p>
  );
}
