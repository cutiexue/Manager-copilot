import { useEffect, useLayoutEffect, useRef } from 'react';
import { hrefFor, type Page, type Route } from '../route';
import { Spring, finePointer, reducedMotion } from '../motion';
import Icon, { type IconName } from './Icon';

interface Props {
  route: Route;
  counts: { decisions: number; atRisk: number; actions: number; alerts: number };
}

type Slot = Exclude<Page, 'chat'>;

const ITEMS: { slot: Slot; label: string; icon: IconName }[] = [
  { slot: 'home', label: 'New chat', icon: 'plus' },
  { slot: 'chats', label: 'Conversations', icon: 'chats' },
  { slot: 'briefing', label: 'Briefing', icon: 'briefing' },
  { slot: 'orders', label: 'Orders & output', icon: 'orders' },
  { slot: 'actions', label: 'Actions', icon: 'actions' },
  { slot: 'watches', label: 'Watches & alerts', icon: 'watch' },
];

// An open conversation belongs to Conversations in the dock.
const slotFor = (route: Route): Slot => (route.page === 'chat' ? 'chats' : route.page);

// Icons grow when the pointer is near: full size at the icon, nothing beyond this distance.
const REACH = 110;
const GROW = 0.38;

// The app's navigation: a floating glass dock at the bottom centre. The current page sits on a glass
// capsule that slides to the next page when it changes, stretching along its path and settling with a
// small bounce; a dot under the icon marks it too. Pointing at the dock enlarges the icon under the
// pointer and, less, its neighbours, and shows the name above it. Every item is a page link.
export default function Dock({ route, counts }: Props) {
  const current = slotFor(route);
  const listRef = useRef<HTMLUListElement>(null);
  const capsuleRef = useRef<HTMLLIElement>(null);
  const itemRefs = useRef<Record<string, HTMLLIElement | null>>({});
  const springs = useRef<{ x: Spring; w: Spring } | null>(null);
  const frame = useRef(0);

  const badge: Partial<Record<Slot, number>> = {
    briefing: counts.decisions || undefined,
    actions: counts.actions || undefined,
    watches: counts.alerts || undefined,
  };

  // Move the capsule under the current item.
  useLayoutEffect(() => {
    const item = itemRefs.current[current];
    const capsule = capsuleRef.current;
    if (!item || !capsule) return;
    const x = item.offsetLeft;
    const w = item.offsetWidth;
    const draw = (sx: Spring, sw: Spring) => {
      const stretch = Math.min(0.45, Math.abs(sx.velocity) / 2200);
      const width = sw.value * (1 + stretch);
      capsule.style.width = `${width}px`;
      capsule.style.transform = `translateX(${sx.value - (width - sw.value) / 2}px) scaleY(${1 - stretch * 0.22})`;
    };
    if (!springs.current || reducedMotion()) {
      springs.current = { x: new Spring(x), w: new Spring(w) };
      draw(springs.current.x, springs.current.w);
      return;
    }
    const { x: sx, w: sw } = springs.current;
    sx.target = x;
    sw.target = w;
    cancelAnimationFrame(frame.current);
    let last = performance.now();
    const tick = (now: number) => {
      const dt = Math.min(1 / 30, (now - last) / 1000);
      last = now;
      sx.step(dt);
      sw.step(dt);
      draw(sx, sw);
      if (sx.settled && sw.settled) {
        sx.jump(x);
        sw.jump(w);
        draw(sx, sw);
      } else frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
  }, [current]);

  useEffect(() => () => cancelAnimationFrame(frame.current), []);

  // Keep the capsule in place when the window is resized.
  useEffect(() => {
    const onResize = () => {
      const item = itemRefs.current[current];
      if (item && springs.current) {
        springs.current.x.jump(item.offsetLeft);
        springs.current.w.jump(item.offsetWidth);
        if (capsuleRef.current) {
          capsuleRef.current.style.width = `${item.offsetWidth}px`;
          capsuleRef.current.style.transform = `translateX(${item.offsetLeft}px)`;
        }
      }
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [current]);

  const magnify = (clientX: number | null) => {
    const list = listRef.current;
    if (!list) return;
    for (const item of ITEMS) {
      const el = itemRefs.current[item.slot];
      if (!el) continue;
      let s = 1;
      if (clientX !== null) {
        const r = el.getBoundingClientRect();
        const d = Math.abs(clientX - (r.left + r.width / 2));
        s = 1 + GROW * Math.max(0, 1 - d / REACH) ** 2;
      }
      el.style.setProperty('--s', s.toFixed(3));
    }
  };

  return (
    <div className="dock-wrap">
      <nav className="dock" aria-label="Main">
        <ul
          ref={listRef}
          onPointerMove={(e) => finePointer() && !reducedMotion() && magnify(e.clientX)}
          onPointerLeave={() => magnify(null)}
        >
          <li ref={capsuleRef} className="dock-capsule" aria-hidden />
          {ITEMS.map((item) => {
            const active = item.slot === current;
            const count = badge[item.slot];
            const body = (
              <>
                <span className="dock-icon">
                  <Icon name={item.icon} size={21} />
                  {count !== undefined && <span className="dock-badge">{count}</span>}
                </span>
                <span className="dock-label" aria-hidden>{item.label}</span>
                {active && <span className="dock-dot" aria-hidden />}
              </>
            );
            return (
              <li key={item.slot} ref={(el) => (itemRefs.current[item.slot] = el)}>
                <a className="dock-item" aria-label={count ? `${item.label}, ${count}` : item.label}
                  href={hrefFor({ page: item.slot })} aria-current={active ? 'page' : undefined}>
                  {body}
                </a>
              </li>
            );
          })}
        </ul>
      </nav>
    </div>
  );
}
