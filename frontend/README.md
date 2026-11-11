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

## Where each page gets its data

Every page reads live data from the backend; only the briefing has an offline fallback.

| Area | Backend endpoints | Notes |
|---|---|---|
| Chat | `GET/POST /sessions`, `GET/POST /sessions/{id}/messages` | Each answer carries its tool calls, cited rows and proposals |
| Morning briefing | `GET /briefings/latest` | Falls back to `src/fixtures/briefing.json` when the backend is unreachable, labelled "snapshot" |
| Evidence drawer | rows cited in the briefing payload or the chat answer | Shows the raw CSV rows behind a claim (`GET /evidence/{id}` serves one row to other clients) |
| Orders & output | the briefing payload | Yesterday's output and at-risk orders |
| Actions | `/actions`, `/reminders`, `/notes`, `/drafts`, `/audit` | Proposals are carried out only after Confirm; the audit log is append-only |
| Watches & alerts | `/watches`, `/alerts`, `/data/snapshot`, `/dev/data/*` | Watches are checked against scripted data snapshots |
| Order search | `GET /orders/search` | Capped results, so it scales with the order book |

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

A floating glass dock at the bottom switches between focused pages; Ctrl+K (⌘K) searches pages,
actions and conversations. Addresses use the
URL hash, so refresh keeps the page and the browser back button works.

| Address | Page |
|---|---|
| `#/` | **New chat** (home): today's top 3 briefing items above a centred chat box, with suggested questions |
| `#/chat/<id>` | An open conversation; past ones are listed beside the chat (and under the dock's *Conversations* button on narrow screens) |
| `#/briefing` | Morning briefing: summary on a dark card, then one module per check; a module opens in place with every item (Evidence, Ask, Remind) |
| `#/orders` | Every order, filtered by due date, status, stage, customer or search; totals and the stage chart come from `GET /orders` |
| `#/actions` | Proposals waiting for Confirm, reminders, order notes, chase-up drafts and the audit log; **New reminder** searches all orders |
| `#/watches` | Standing watches, the alerts they raised, and the scripted data snapshot they are checked against |

"Ask" buttons on any page open a new conversation with the question typed in but not sent.
"Remind…" and "New reminder" open one dialog: the order is preset or searched for, and nothing is
recorded until the manager confirms or cancels.

Look: the Neumorphism Light palette (#E0E5EC surface, #FFFFFF highlight, #A3B1C6 shadow, #4D5B70
and #6D7C94 slate): raised cards from paired shadows, frosted panels, one dark slate card per page.
Red and amber are used only for status marks. Buttons: dark slate for the main action (Send,
Confirm, New reminder), raised light buttons for secondary controls, slate text with an icon for
per-item actions (Evidence, Ask, Remind).
Motion only answers the pointer or a click, and is switched off with the system's reduced-motion
setting; glass turns solid with reduced transparency. The Actions and Watches pages reload every
30 seconds and when the window regains focus.
The evidence drawer and the confirm dialog open over whichever page is showing.

## Layout (plan §12)

```
src/
├── App.tsx                    shell, pages and shared state (briefing, conversations, counts)
├── route.ts                   hash routes (#/, #/chat/<id>, #/briefing, #/orders, #/actions, #/watches)
├── api.ts                     backend client (via /api proxy)
├── types.ts                   backend response shapes
├── evidence.ts                tool output → evidence drawer view, Ask questions
├── dates.ts                   date formatting (UTC, so weekdays never shift)
├── theme.ts                   light / dark / system theme
├── motion.ts                  springs, rolling numbers, glass pointer light, view transitions
├── useAutoRefresh.ts          30-second and on-focus reload for the Actions and Watches pages
├── fixtures/briefing.json     briefing snapshot (offline fallback)
└── components/
    ├── TopBar.tsx             brand, data date, reminders clock, search (Ctrl+K), theme switch
    ├── Dock.tsx               bottom glass dock: pages, counts, recent conversations
    ├── ChatSidebar.tsx        past conversations beside the chat (wide screens)
    ├── CommandPalette.tsx     Ctrl+K search over pages, actions and conversations
    ├── ThemeSwitch.tsx        light / dark / system control
    ├── TodayDigest.tsx        home: briefing headline and suggested questions
    ├── Headline.tsx           the briefing's one-line headline
    ├── Narrative.tsx          the briefing's three sentences, each opening its source rows
    ├── BriefingSummary.tsx    briefing page: dark summary card, modules that open in place
    ├── LevelMark.tsx          act-now / watch marks (shape and colour)
    ├── YesterdayStrip.tsx     yesterday's output per stage against recent workdays
    ├── OrdersPage.tsx         Orders & output: filters, backend totals, stage chart, order list
    ├── LiquidFilter.tsx       due-date filter: one capsule that splits into options
    ├── Segmented.tsx          segmented control with a sliding capsule
    ├── Chat.tsx               multi-turn chat, error states, per-answer sources
    ├── Markdown.tsx           safe Markdown rendering of model answers; long tables expand
    ├── ProposalCard.tsx       a proposed follow-up waiting for Confirm
    ├── EvidenceDrawer.tsx     claim, calculation, source rows
    ├── ConfirmModal.tsx       reminder dialog: preset or searched order, explicit confirm
    ├── OrderPicker.tsx        order search combobox (keyboard: Up/Down, Enter)
    ├── FollowUps.tsx          Actions page
    ├── Watches.tsx            Watches & alerts page
    ├── WatchModal.tsx         new watch dialog, explicit confirm
    └── Icon.tsx               shared stroke icons
```
