import { useLayoutEffect, useRef, useState } from 'react';

interface Props<T extends string> {
  label: string;
  options: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
}

// A segmented control whose glass capsule slides to the chosen segment.
export default function Segmented<T extends string>({ label, options, value, onChange }: Props<T>) {
  const ref = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState<{ x: number; w: number } | null>(null);

  useLayoutEffect(() => {
    const measure = () => {
      const el = ref.current?.querySelector<HTMLElement>('[aria-checked="true"]');
      if (el) setBox({ x: el.offsetLeft, w: el.offsetWidth });
    };
    measure();
    window.addEventListener('resize', measure);
    return () => window.removeEventListener('resize', measure);
  }, [value, options]);

  return (
    <div ref={ref} className="segmented" role="radiogroup" aria-label={label}>
      {box && <span className="segmented-capsule" style={{ width: box.w, transform: `translateX(${box.x}px)` }} aria-hidden />}
      {options.map((o) => (
        <button key={o.value} type="button" role="radio" aria-checked={o.value === value} className="segment"
          onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}
