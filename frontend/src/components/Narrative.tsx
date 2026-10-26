import type { Briefing, EvidenceView, NarrativeSentence } from '../types';

const TOPIC: Record<NarrativeSentence['topic'], string> = { yesterday: 'Yesterday', at_risk: 'At risk', today: 'Today' };

// The briefing in three sentences under the headline, one per line: yesterday, at risk, today.
// The text comes from the backend as written; a sentence with source rows opens them when clicked.
export default function Narrative({ briefing, onEvidence }: { briefing: Briefing; onEvidence: (v: EvidenceView) => void }) {
  const sentences = briefing.narrative?.sentences ?? [];
  if (sentences.length === 0) return null; // briefings produced before the narrative existed

  return (
    <p className="narrative">
      {sentences.map((s) => {
        const refs = s.evidence?.source_rows ?? [];
        if (refs.length === 0) {
          return (
            <span key={s.topic} className="narrative-line">
              {s.text}{' '}
            </span>
          );
        }
        const open = () => onEvidence({ title: TOPIC[s.topic] ?? s.topic, claim: s.text, calculation: [], refs });
        return (
          <span key={s.topic} className="narrative-line">
            <span
              className="narrative-s"
              role="button"
              tabIndex={0}
              title="Source rows"
              onClick={open}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  open();
                }
              }}
            >
              {s.text}
            </span>{' '}
          </span>
        );
      })}
    </p>
  );
}
