# Manager Co-Pilot — Frontend (Member F)

React + TypeScript + Vite. Built against the backend in `../backend` (originally the `src` branch).

## Run

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
```

For live chat, start the backend in another terminal:

```bash
cd backend
python main.py --api # serves 127.0.0.1:8000; Vite proxies /api/* to it
```

Without the backend the page still loads: the briefing falls back to the saved snapshot
(header pill "Briefing: snapshot") and the chat panel shows a "Backend offline" state.

Other commands: `npm run typecheck`, `npm run build`.

## What is real and what is not yet

| Area | Source | Status |
|---|---|---|
| Chat | `GET/POST /sessions`, `GET/POST /sessions/{id}/messages` (api.py) | **Live** backend calls |
| Morning briefing | `GET /briefings/latest` (api.py → `briefing.get_briefing_payload()`) | **Live**; falls back to `src/fixtures/briefing.json` when the backend is unreachable, labelled "snapshot" |
| Evidence drawer | source rows cited by the tools, resolved to the raw CSV rows | Comes with the briefing payload (live or snapshot) |
| Create reminder + confirm | in-browser state only | **Demo**: backend has no action/confirm endpoint yet |
| Watches, feasibility, order detail, audit API | — | Not started; waiting for backend endpoints |

The UI never computes business numbers. Every figure shown is copied from a tool
output field (see `src/evidence.ts`).

## Regenerate the briefing snapshot

```bash
# run from frontend/; ../backend holds briefing.py and track1/data/*.csv
python3 scripts/make_briefing_fixture.py ../backend [as_of_date]
```

The snapshot is only the offline fallback. `GET /briefings/latest` returns the same
shape, and a backend test asserts that the live payload still equals this file — when
it fails, regenerate the snapshot.

## Pages

A sidebar (like Claude or ChatGPT) switches between focused pages. Addresses use the
URL hash, so refresh keeps the page and the browser back button works.

| Address | Page |
|---|---|
| `#/` | **New chat** (home): today's top 3 briefing items above a centred chat box, with suggested questions |
| `#/chat/<id>` | An open conversation; the sidebar's *Recent* list holds saved conversations |
| `#/briefing` | Full morning briefing (all items, evidence, Ask Co-Pilot, Create reminder) |
| `#/orders` | Yesterday's output and at-risk orders |
| `#/actions` | Action log (demo, browser only) |

"Ask" buttons on any page open a new conversation with the question typed in but not sent.
The evidence drawer and the confirm dialog open over whichever page is showing. Below 860 px
the sidebar becomes a slide-in menu.

## Layout (plan §12)

```
src/
├── App.tsx                    shell, pages and shared state (briefing, conversations, actions)
├── route.ts                   hash routes (#/, #/chat/<id>, #/briefing, #/orders, #/actions)
├── api.ts                     backend client (via /api proxy)
├── types.ts                   backend response shapes
├── evidence.ts                tool output → evidence drawer view, Ask questions
├── fixtures/briefing.json     briefing snapshot (offline fallback)
└── components/
    ├── Sidebar.tsx            new chat, page links, recent conversations, data status
    ├── TodayDigest.tsx        home: top-3 briefing items and suggested questions
    ├── BriefingSummary.tsx    full briefing page, concise first
    ├── DetailPanel.tsx        yesterday's output / at-risk orders
    ├── Chat.tsx               multi-turn chat, error states
    ├── EvidenceDrawer.tsx     claim, calculation, source rows
    ├── ConfirmModal.tsx       explicit confirm before any action
    ├── ActionLog.tsx          proposed/confirmed/cancelled log
    └── TypeBadge.tsx          finding type: text + symbol, not colour only
```
