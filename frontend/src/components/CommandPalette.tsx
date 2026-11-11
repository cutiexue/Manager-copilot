import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import Icon, { type IconName } from './Icon';

export interface Command {
  id: string;
  label: string;
  group: 'Pages' | 'Actions' | 'Conversations';
  icon: IconName;
  run: () => void;
}

interface Props {
  commands: Command[];
  onClose: () => void;
}

/** The label with every part that matches a query word wrapped in <mark>. */
function highlight(label: string, words: string[]): ReactNode {
  if (words.length === 0) return label;
  const pattern = new RegExp(`(${words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'gi');
  return label.split(pattern).map((part, i) => (i % 2 === 1 ? <mark key={i}>{part}</mark> : part));
}

// Ctrl+K (⌘K on a Mac): a search box low in the middle of the screen over a dimmed, blurred page.
// Typing filters pages, actions and conversations and highlights what matched; arrow keys move,
// Enter opens, Escape closes. It opens and closes without animation, because it is a keyboard tool
// people use many times a day and any motion would only slow it down.
export default function CommandPalette({ commands, onClose }: Props) {
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const listRef = useRef<HTMLUListElement>(null);
  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);

  const shown = useMemo(
    () => commands.filter((c) => words.every((w) => c.label.toLowerCase().includes(w))),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [commands, query],
  );

  useEffect(() => setActive(0), [query]);
  useEffect(() => {
    listRef.current?.querySelector<HTMLElement>(`[data-index="${active}"]`)?.scrollIntoView({ block: 'nearest' });
  }, [active]);

  const choose = (c: Command | undefined) => {
    if (!c) return;
    onClose();
    c.run();
  };

  let lastGroup = '';
  return (
    <div className="palette-scrim" onMouseDown={onClose}>
      <div
        className="palette"
        role="dialog"
        aria-modal="true"
        aria-label="Search"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="palette-input">
          <Icon name="search" size={18} />
          <input
            autoFocus
            value={query}
            placeholder="Search pages, actions and conversations…"
            aria-label="Search"
            aria-controls="palette-list"
            aria-activedescendant={shown[active] ? `cmd-${shown[active].id}` : undefined}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'ArrowDown') {
                e.preventDefault();
                setActive((i) => Math.min(shown.length - 1, i + 1));
              } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                setActive((i) => Math.max(0, i - 1));
              } else if (e.key === 'Enter') {
                e.preventDefault();
                choose(shown[active]);
              } else if (e.key === 'Escape') {
                e.preventDefault();
                onClose();
              }
            }}
          />
          <kbd>Esc</kbd>
        </div>
        {shown.length === 0 ? (
          <p className="palette-empty">Nothing matches “{query}”. Try a page name or a conversation title.</p>
        ) : (
          <ul id="palette-list" ref={listRef} role="listbox" className="palette-list">
            {shown.map((c, i) => {
              const head = c.group !== lastGroup ? c.group : null;
              lastGroup = c.group;
              return (
                <li key={c.id} role="presentation">
                  {head && <p className="palette-group">{head}</p>}
                  <div
                    id={`cmd-${c.id}`}
                    role="option"
                    aria-selected={i === active}
                    data-index={i}
                    className="palette-item"
                    onMouseMove={() => setActive(i)}
                    onClick={() => choose(c)}
                  >
                    <Icon name={c.icon} size={16} />
                    <span className="palette-label">{highlight(c.label, words)}</span>
                    {i === active && <span className="palette-enter">↵</span>}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
