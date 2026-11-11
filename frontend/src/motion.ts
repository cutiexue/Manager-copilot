import { useEffect, useRef, useState, type RefObject } from 'react';

// Shared motion helpers. Every effect here is skipped when the system asks for reduced motion,
// and pointer effects only run with a real mouse (no sticky hover on touch screens).

export const reducedMotion = () => !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
export const finePointer = () => !!window.matchMedia?.('(hover: hover) and (pointer: fine)').matches;

/**
 * A damped spring stepped once per frame. Damping ratio about 0.7 gives one small overshoot,
 * which is the "settle with a bounce" the dock capsule uses; 1.0 would settle without one.
 */
export class Spring {
  value: number;
  velocity = 0;
  target: number;
  constructor(value: number, readonly stiffness = 420, readonly damping = 29) {
    this.value = value;
    this.target = value;
  }
  step(dt: number) {
    const force = this.stiffness * (this.target - this.value) - this.damping * this.velocity;
    this.velocity += force * dt;
    this.value += this.velocity * dt;
  }
  get settled() {
    return Math.abs(this.target - this.value) < 0.05 && Math.abs(this.velocity) < 0.05;
  }
  jump(value: number) {
    this.value = this.target = value;
    this.velocity = 0;
  }
}

/** Counts from the value on screen to the new one (about half a second, fast start, soft end). */
export function useRollingNumber(value: number, duration = 520): number {
  const [shown, setShown] = useState(value);
  const from = useRef(value);
  const current = useRef(value);

  useEffect(() => {
    if (reducedMotion() || current.current === value) {
      current.current = value;
      setShown(value);
      return;
    }
    from.current = current.current;
    const start = performance.now();
    let frame = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 4);
      current.current = from.current + (value - from.current) * eased;
      setShown(t === 1 ? value : current.current);
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value, duration]);

  return shown;
}

/**
 * Glass card pointer effect: a soft light follows the cursor inside the card, its rim brightens
 * nearest the cursor, and the card tilts towards it by at most 4 degrees. The tilt eases towards
 * the pointer each frame instead of jumping, and eases back flat when the pointer leaves.
 */
export function useGlassPointer<T extends HTMLElement>(ref: RefObject<T>, maxTilt = 4) {
  useEffect(() => {
    const el = ref.current;
    if (!el || !finePointer() || reducedMotion()) return;
    let frame = 0;
    let rx = 0, ry = 0, tx = 0, ty = 0;
    const loop = () => {
      rx += (tx - rx) * 0.14;
      ry += (ty - ry) * 0.14;
      el.style.transform = `perspective(900px) rotateX(${rx.toFixed(3)}deg) rotateY(${ry.toFixed(3)}deg)`;
      if (Math.abs(tx - rx) > 0.01 || Math.abs(ty - ry) > 0.01) frame = requestAnimationFrame(loop);
      else {
        frame = 0;
        if (tx === 0 && ty === 0) el.style.transform = '';
      }
    };
    const kick = () => {
      if (!frame) frame = requestAnimationFrame(loop);
    };
    const move = (e: PointerEvent) => {
      const r = el.getBoundingClientRect();
      const x = e.clientX - r.left;
      const y = e.clientY - r.top;
      el.style.setProperty('--mx', `${x}px`);
      el.style.setProperty('--my', `${y}px`);
      // Large cards tilt less, so their far edge never swings a long way.
      const scale = Math.min(1, 360 / Math.max(r.width, r.height));
      ty = ((x / r.width) - 0.5) * 2 * maxTilt * scale;
      tx = -((y / r.height) - 0.5) * 2 * maxTilt * scale;
      kick();
    };
    const enter = () => el.classList.add('is-lit');
    const leave = () => {
      el.classList.remove('is-lit');
      tx = ty = 0;
      kick();
    };
    el.addEventListener('pointermove', move);
    el.addEventListener('pointerenter', enter);
    el.addEventListener('pointerleave', leave);
    return () => {
      cancelAnimationFrame(frame);
      el.removeEventListener('pointermove', move);
      el.removeEventListener('pointerenter', enter);
      el.removeEventListener('pointerleave', leave);
      el.style.transform = '';
    };
  }, [ref, maxTilt]);
}

/**
 * Runs a DOM update inside a view transition when the browser has them, so a module can grow
 * from where it sits and shrink back along the same path. Without support, or with reduced
 * motion, the update simply happens.
 */
export function withViewTransition(update: () => void) {
  const doc = document as Document & { startViewTransition?: (cb: () => void) => unknown };
  if (!doc.startViewTransition || reducedMotion()) {
    update();
    return;
  }
  doc.startViewTransition(update);
}
