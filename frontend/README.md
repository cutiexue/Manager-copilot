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

Without the backend the page still loads; the chat panel shows a "Backend offline" state.

Other commands: `npm run typecheck`, `npm run build`.

## What is real and what is not yet

| Area | Source | Status |
|---|---|---|
| Chat | `GET/POST /sessions`, `GET/POST /sessions/{id}/messages` (api.py) | **Live** backend calls |
| Morning briefing | `src/fixtures/briefing.json` — verbatim output of `briefing.get_morning_briefing()` | **Snapshot**: backend has no briefing endpoint yet |
| Evidence drawer | source rows cited by the tools, resolved to the raw CSV rows | Snapshot (same fixture) |
| Create reminder + confirm | in-browser state only | **Demo**: backend has no action/confirm endpoint yet |
| Watches, feasibility, order detail, audit API | — | Not started; waiting for backend endpoints |

The UI never computes business numbers. Every figure shown is copied from a tool
output field (see `src/evidence.ts`).

## Regenerate the briefing snapshot

```bash
# run from frontend/; ../backend holds briefing.py and track1/data/*.csv
python3 scripts/make_briefing_fixture.py ../backend [as_of_date]
```

When the backend adds e.g. `GET /briefings/latest`, replace the fixture import in
`src/App.tsx` with an API call — the types in `src/types.ts` already match the
briefing structure.

## Layout (plan §12)

```
src/
├── App.tsx                    page layout and state
├── api.ts                     backend client (via /api proxy)
├── types.ts                   backend response shapes
├── evidence.ts                tool output → evidence drawer view
├── fixtures/briefing.json     briefing snapshot
└── components/
    ├── BriefingSummary.tsx    top-3 items, concise first
    ├── DetailPanel.tsx        yesterday's output / at-risk orders
    ├── Chat.tsx               multi-turn chat, sessions, error states
    ├── EvidenceDrawer.tsx     claim, calculation, source rows
    ├── ConfirmModal.tsx       explicit confirm before any action
    ├── ActionLog.tsx          proposed/confirmed/cancelled log
    └── TypeBadge.tsx          finding type: text + symbol, not colour only
```
