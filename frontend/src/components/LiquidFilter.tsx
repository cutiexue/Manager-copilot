import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from 'react';

interface Option<T extends string> {
  value: T;
  label: string;
}

interface Props<T extends string> {
  label: string;
  options: Option<T>[];
  value: T;
  onChange: (value: T) => void;
}

const GAP = 6;
// The closed capsule is a little wider, for its chevron.
const CHEVRON = 16;

// A filter that rests as one glass capsule showing the current choice. Opening it splits the
// capsule into one capsule per option, like a drop of liquid metal dividing; choosing one draws
// the others back into it. The liquid look comes from an SVG "goo" filter on the capsule shapes
// only, so the labels on top stay sharp.
export default function LiquidFilter<T extends string>({ label, options, value, onChange }: Props<T>) {
  const [open, setOpen] = useState(false);
  const [widths, setWidths] = useState<number[] | null>(null);
  const measureRef = useRef<HTMLSpanElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const selected = Math.max(0, options.findIndex((o) => o.value === value));

  useLayoutEffect(() => {
    const spans = measureRef.current?.querySelectorAll('span');
    if (spans) setWidths(Array.from(spans, (s) => Math.ceil(s.getBoundingClientRect().width)));
  }, [options]);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === 'Escape' : !rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener('mousedown', close);
    window.addEventListener('keydown', close);
    return () => {
      window.removeEventListener('mousedown', close);
      window.removeEventListener('keydown', close);
    };
  }, [open]);

  const offsets: number[] = [];
  (widths ?? []).reduce((x, w, i) => ((offsets[i] = x), x + w + GAP), 0);
  const total = widths ? widths.reduce((a, b) => a + b, 0) + GAP * (widths.length - 1) : 0;
  const closedWidth = widths ? widths[selected] + CHEVRON : 0;
  const width = widths ? (open ? total : closedWidth) : undefined;

  return (
    <div ref={rootRef} className={`liquid${open ? ' is-open' : ''}`} style={{ width } as CSSProperties}>
      <span ref={measureRef} className="liquid-measure" aria-hidden>
        {options.map((o) => (
          <span key={o.value}>{o.label}</span>
        ))}
      </span>
      <svg className="liquid-defs" aria-hidden width="0" height="0">
        <filter id="liquid-goo">
          <feGaussianBlur in="SourceGraphic" stdDeviation="7" result="blur" />
          <feColorMatrix in="blur" mode="matrix" values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 22 -9" result="goo" />
          <feComposite in="SourceGraphic" in2="goo" operator="atop" />
        </filter>
      </svg>
      {widths && (
        <>
          <span className="liquid-blobs" aria-hidden>
            {options.map((o, i) => (
              <span
                key={o.value}
                className="liquid-blob"
                style={{
                  width: open ? widths[i] : closedWidth,
                  transform: `translateX(${open ? offsets[i] : 0}px)`,
                  transitionDelay: open ? `${i * 18}ms` : '0ms',
                }}
              />
            ))}
          </span>
          {open ? (
            <span className="liquid-options" role="radiogroup" aria-label={label}>
              {options.map((o, i) => (
                <button
                  key={o.value}
                  type="button"
                  role="radio"
                  aria-checked={i === selected}
                  className="liquid-option"
                  style={{ width: widths[i], transform: `translateX(${offsets[i]}px)` }}
                  autoFocus={i === selected}
                  onClick={() => {
                    onChange(o.value);
                    setOpen(false);
                  }}
                >
                  {o.label}
                </button>
              ))}
            </span>
          ) : (
            <button
              type="button"
              className="liquid-option liquid-current"
              aria-haspopup="true"
              aria-expanded={false}
              aria-label={`${label}: ${options[selected].label}`}
              style={{ width: closedWidth }}
              onClick={() => setOpen(true)}
            >
              {options[selected].label}
            </button>
          )}
        </>
      )}
    </div>
  );
}
