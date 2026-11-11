import { useState, type ReactNode } from 'react';

// The subset of Markdown a model answer uses: paragraphs, headings, bullet and numbered lists,
// tables, code and links. Output is built as React elements (never raw HTML), so text from the
// model cannot inject markup; links open only for http(s) addresses.

const INLINE = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*\s][^*]*\*)|(\[[^\]]+\]\((https?:\/\/[^\s)]+)\))/g;

function inline(text: string, key: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let n = 0;
  for (const match of text.matchAll(INLINE)) {
    const at = match.index ?? 0;
    if (at > last) out.push(text.slice(last, at));
    const token = match[0];
    const k = `${key}-${n++}`;
    if (match[1]) out.push(<code key={k}>{token.slice(1, -1)}</code>);
    else if (match[2]) out.push(<strong key={k}>{inline(token.slice(2, -2), k)}</strong>);
    else if (match[3]) out.push(<em key={k}>{token.slice(1, -1)}</em>);
    else
      out.push(
        <a key={k} href={match[5]} target="_blank" rel="noreferrer">
          {token.slice(1, token.indexOf(']('))}
        </a>,
      );
    last = at + token.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

const cells = (row: string) =>
  row
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((c) => c.trim());

const isDivider = (line: string) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$/.test(line);
const BULLET = /^\s*[-*•]\s+/;
const NUMBER = /^\s*\d+[.)]\s+/;
const startsBlock = (line: string, next?: string) =>
  line.startsWith('```') || /^#{1,4}\s/.test(line) || BULLET.test(line) || NUMBER.test(line) ||
  (line.includes('|') && next !== undefined && isDivider(next));

export default function Markdown({ text }: { text: string }) {
  const lines = text.replace(/\r\n?/g, '\n').split('\n');
  const blocks: ReactNode[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const key = `b${i}`;
    if (!line.trim()) {
      i += 1;
    } else if (line.startsWith('```')) {
      const code: string[] = [];
      i += 1;
      while (i < lines.length && !lines[i].startsWith('```')) code.push(lines[i++]);
      i += 1;
      blocks.push(
        <pre key={key}>
          <code>{code.join('\n')}</code>
        </pre>,
      );
    } else if (/^#{1,4}\s/.test(line)) {
      blocks.push(
        <p key={key} className="md-heading">
          {inline(line.replace(/^#{1,4}\s+/, ''), key)}
        </p>,
      );
      i += 1;
    } else if (line.includes('|') && i + 1 < lines.length && isDivider(lines[i + 1])) {
      const head = cells(line);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && lines[i].includes('|') && lines[i].trim()) rows.push(cells(lines[i++]));
      blocks.push(<MdTable key={key} id={key} head={head} rows={rows} />);
    } else if (BULLET.test(line) || NUMBER.test(line)) {
      const ordered = NUMBER.test(line);
      const marker = ordered ? NUMBER : BULLET;
      const items: string[] = [];
      while (i < lines.length && lines[i].trim()) {
        if (marker.test(lines[i])) items.push(lines[i].replace(marker, ''));
        else if (/^\s{2,}\S/.test(lines[i]) && items.length) items[items.length - 1] += ` ${lines[i].trim()}`;
        else break;
        i += 1;
      }
      const List = ordered ? 'ol' : 'ul';
      blocks.push(
        <List key={key}>
          {items.map((item, n) => (
            <li key={n}>{inline(item, `${key}i${n}`)}</li>
          ))}
        </List>,
      );
    } else {
      const para: string[] = [];
      while (i < lines.length && lines[i].trim() && !(para.length && startsBlock(lines[i], lines[i + 1]))) {
        para.push(lines[i++]);
      }
      blocks.push(
        <p key={key}>
          {para.map((p, n) => (
            <span key={n}>
              {n > 0 && <br />}
              {inline(p, `${key}p${n}`)}
            </span>
          ))}
        </p>,
      );
    }
  }
  return <div className="md">{blocks}</div>;
}

// Rows past this many wait behind "Show all".
const TABLE_ROWS = 8;
const NUMERIC = /^[\s\d,.%+\-−–()]+$/;

// A table in an answer. Text columns wrap instead of running off the card; the table scrolls
// sideways only when its columns truly do not fit. Long tables show their first rows first.
function MdTable({ id, head, rows }: { id: string; head: string[]; rows: string[][] }) {
  const [open, setOpen] = useState(false);
  const shown = open ? rows : rows.slice(0, TABLE_ROWS);
  const numeric = head.map((_, c) => rows.length > 0 && rows.every((r) => !r[c] || NUMERIC.test(r[c])));
  return (
    <div className="md-table">
      <div className="table-scroll">
        <table className="table small">
          <thead>
            <tr>
              {head.map((h, c) => (
                <th key={c} scope="col" className={numeric[c] ? 'num' : undefined}>
                  {inline(h, `${id}h${c}`)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((row, r) => (
              <tr key={r}>
                {head.map((_, c) => (
                  <td key={c} className={numeric[c] ? 'num' : undefined}>{inline(row[c] ?? '', `${id}r${r}c${c}`)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length > TABLE_ROWS && (
        <button className="link" aria-expanded={open} onClick={() => setOpen(!open)}>
          {open ? 'Show fewer rows' : `Show all ${rows.length} rows`}
        </button>
      )}
    </div>
  );
}
