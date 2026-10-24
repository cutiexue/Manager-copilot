import type { CSSProperties } from 'react';
import type { Briefing, EvidenceView, YesterdayStage } from '../types';
import { evidenceForStage } from '../evidence';
import { shortDate } from '../dates';

interface Props {
  briefing: Briefing;
  onEvidence: (v: EvidenceView) => void;
}

/** A percentage from the backend, only formatted: one decimal and a real minus sign. */
function signedPercent(value: number): string {
  const digits = Math.abs(value).toFixed(1);
  if (digits === '0.0') return '0.0%';
  return `${value < 0 ? '−' : '+'}${digits}%`;
}

const W = 160;
const H = 34;
const PAD = 4;

// The stage's recent workdays drawn from zero, so a real drop looks big and day-to-day noise stays
// small. The hairline is the baseline average and the dot is yesterday. Hovering a day shows its value;
// the full numbers are in the evidence drawer the tile opens.
function Sparkline({ stage, date }: { stage: YesterdayStage; date: string }) {
  const days = [
    ...(stage.baseline_records ?? []).map((r) => ({ date: r.date, value: r.pieces_completed })),
    ...(stage.pieces_completed !== undefined ? [{ date, value: stage.pieces_completed }] : []),
  ].sort((a, b) => a.date.localeCompare(b.date));
  if (days.length < 2) return null;

  const top = Math.max(...days.map((d) => d.value), stage.baseline_average ?? 0) || 1;
  const step = (W - 2 * PAD) / (days.length - 1);
  const x = (i: number) => PAD + i * step;
  const y = (v: number) => H - PAD - (v / top) * (H - 2 * PAD);
  const end = { x: x(days.length - 1), y: y(days[days.length - 1].value) };

  return (
    <svg className="spark" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden>
      {stage.baseline_average !== undefined && (
        <line className="spark-avg" x1={PAD} x2={W - PAD} y1={y(stage.baseline_average)} y2={y(stage.baseline_average)} />
      )}
      <polyline className="spark-line" points={days.map((d, i) => `${x(i)},${y(d.value)}`).join(' ')} />
      <line className="spark-dot" x1={end.x} x2={end.x} y1={end.y} y2={end.y} />
      {days.map((d, i) => (
        <rect key={d.date} className="spark-hit" x={x(i) - step / 2} y={0} width={step} height={H}>
          <title>{`${shortDate(d.date)} · ${d.value.toLocaleString('en-US')} pcs`}</title>
        </rect>
      ))}
    </svg>
  );
}

function StageTile({ stage, date, onEvidence }: { stage: YesterdayStage; date: string; onEvidence: Props['onEvidence'] }) {
  const pieces = stage.pieces_completed;
  const change = stage.change_percent;
  const delta = change != null ? signedPercent(change) : null;
  const spoken =
    pieces === undefined
      ? `${stage.stage}: ${stage.output_status ?? 'no data'}`
      : `${stage.stage} ${pieces} pieces${delta ? `, ${delta} vs ${stage.baseline_workdays}-workday average` : ''}`;

  return (
    <button className="tile" onClick={() => onEvidence(evidenceForStage(date, stage))} aria-label={`${spoken}. Evidence`}>
      <span className="tile-label">{stage.stage}</span>
      <span className="tile-figures">
        <span className="tile-value">{pieces?.toLocaleString('en-US') ?? '—'}</span>
        <span className="tile-delta">{delta ?? stage.output_status ?? ''}</span>
      </span>
      <Sparkline stage={stage} date={date} />
    </button>
  );
}

// The last workday's output per stage (yesterday, or Saturday on a Monday), the way a daily
// production report opens: a figure, the change against the usual level, and the recent trend.
// Each tile opens the rows behind it.
export default function YesterdayStrip({ briefing, onEvidence }: Props) {
  const y = briefing.yesterday;
  const workdays = y.stages.find((s) => s.baseline_workdays)?.baseline_workdays;

  return (
    <div className="strip">
      <div className="strip-head">
        <span className="strip-title">
          {y.label ?? 'Yesterday'}
          <span className="strip-date">{shortDate(y.date)}</span>
        </span>
        {y.is_workday && workdays && <span className="strip-note">pieces · vs {workdays}-workday avg</span>}
      </div>
      {y.is_workday ? (
        <div className="tiles" style={{ '--tiles': y.stages.length } as CSSProperties}>
          {y.stages.map((s) => (
            <StageTile key={s.stage} stage={s} date={y.date} onEvidence={onEvidence} />
          ))}
        </div>
      ) : (
        <p className="strip-rest" title={y.message}>
          Scheduled rest day
        </p>
      )}
    </div>
  );
}
