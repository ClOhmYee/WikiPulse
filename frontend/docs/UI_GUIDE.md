# WikiPulse workspace UI guide

This guide records the implemented post-onboarding frontend. Its interaction mode is **Operate** for searching, filtering, selecting and saving; issue report and stock detail surfaces use **Read** for following context and evidence. The existing four-scene onboarding remains a separate **Persuade** experience governed by [DESIGN.md](../DESIGN.md). This guide does not replace its composition or motion rules.

The app is a Vite/React frontend. Its default mock mode reads synthetic fixtures; its API mode reads HTTP responses through the existing client contract. Discussion and saved-item state remain local. [API_SPEC.md](./API_SPEC.md) and [openapi.yaml](./openapi.yaml) describe the older proposal still used by that client; future backend integration must follow the [repository API specification](../../docs/api-v0.1.md). Page URL changes do not change that HTTP contract or establish a live backend integration.

## User flow and routes

The principal journey is onboarding → Pulse Map or issue search → issue report → related stocks → locally saved items. Supporting document links open Wikipedia sources in a new tab; there is no standalone document detail page. Global search offers issue and stock destinations. The report retains its discussion tab and local discussion state. The canonical page inventory is [PAGES.md](../../docs/frontend/PAGES.md).

| Hash route | Owner | Implemented purpose |
|---|---|---|
| `#/` | `App.jsx`, `NodeField.jsx` | Existing introduction and entry into the workspace |
| `#/pulse` | `pages/pulse/PulsePage.jsx`, `PulseMap.jsx` | Date/snapshot selection, HOT/NEW, document graph, zoom/pan/reset, snapshot summary and document evidence |
| `#/issues`, `#/issues?q=…` | `ExplorePage.jsx` | Card/list presentation switch (default list), search, category filtering and sorting; switching preserves state |
| `#/issues/{issueId}` | `EventPage.jsx` | Report with overview, timeline, news, evidence and discussion; chart range/baseline; source selection; related stocks and saving |
| `#/issues/{issueId}/stocks` | `StocksPage.jsx` | Issue-scoped stock directory with industry and relationship filters |
| `#/stocks` | `StocksPage.jsx` | Stock search, industry and saved-only filters, sorting |
| `#/stocks/{symbol}` | `StocksPage.jsx` | Related event timeline, relationship paths, example price chart and stock saving |
| `#/saved` | `SavedPage.jsx` | Saved event/stock switches, local search and removal |
| `#/mypage` | `AccountPage.jsx` | Account feature notice; links to saved items, login and signup |
| `#/login` | `AccountPage.jsx` | Login availability notice; no authentication or credential input |
| `#/signup` | `AccountPage.jsx` | Signup availability notice; no account creation or credential input |

`app/App.jsx` with `app/router.js` reads `window.location.hash` and listens for `hashchange`; links use these hashes rather than server routes. It parses the optional query separately and supplies `q` as the initial explore search. Unrecognized routes and unknown fixture IDs have recovery links. Detail navigation selects the event-exploration menu context. Browser back/forward changes the hash normally; filters and detail tab state are React state, not a URL serialization contract.

## Visual tokens and typography

The workspace carries the onboarding's dark slate, muted teal and gold into a denser interface. CSS is the implementation source of truth: inherited primitives are in `src/pages/onboarding/onboarding.css`; shell and common controls are in `src/styles/workspace.css`; detail and stock refinements are in `src/styles/details.css` and `src/pages/stocks/stocks.css`.

| Token / value | Current role |
|---|---|
| `--slate: #050a0f` | App background and header |
| `--paper: #f3f7f7` | Primary text |
| `--muted: #9cafb6` | Secondary copy and labels |
| `--teal: #86c9c4` | Primary actions, current navigation, selected controls and chart series |
| `--gold: #dbb057` | Focus outlines, saved icon state, baseline series and demo indicator |
| `--wp-surface: #0b141b` | Bordered content panels |
| `--wp-raised: #101d25` | Declared workspace surface token |
| `--wp-border: #24313a` | Dividers and panel/control edges |
| `--wp-subtle: #7c939e` | Declared subdued workspace color |

Category colors come from the common category response and are passed to `CategoryTag` and map clusters. They identify topics; they do not encode investment recommendations. Detail CSS repeats equivalent `--dt-*` values locally, so edits must account for both scopes.

The inherited typeface is `"Noto Sans KR Variable", "Noto Sans KR", sans-serif`, loaded locally through Fontsource in `main.jsx`. The workspace wordmark uses Barlow Condensed at 27px/600; smaller English identity elements also use Barlow. Base workspace copy is 14px with 1.6 line height and −.015em tracking. Shell headings are 30px/550, 19px/550 and 16px/550. Detail-page titles use `clamp(28px, 3.1vw, 45px)` at weight 650 and 1.35 line height; detail paragraphs use 14px/1.9. Metrics use tabular numerals. Korean headings and prose combine `word-break: keep-all` with overflow wrapping.

## Layout, depth and shapes

The desktop shell uses a fixed 214px left sidebar and a 78px top header containing breadcrumbs, global search and the demo-data disclosure. The header participates in page flow. The content column is capped at 1660px with default page padding `38px 36px 48px`. Pulse Map uses a flexible map beside a 304px preview; event rows remain divider-based lists. Issue reports and stock details use a primary reading column with supporting information beside it until their responsive rules collapse the layout.

| Viewport rule | Implemented adaptation |
|---|---|
| `min-width: 1600px` | Sidebar 236px, page horizontal padding 50px, map preview 350px |
| `max-width: 1199px` | Sidebar 184px, page horizontal padding 25px, map preview 270px |
| `max-width: 960px` | Sidebar 75px with icon navigation; accessible names remain; header 68px and map preview 250px. Stock detail becomes one main column. |
| `max-width: 720px` | Sidebar becomes a 67px bottom navigation plus safe-area inset; header 65px; page horizontal padding 20px; map and preview stack. The mobile map reserves the strip below its SVG for legend and controls. |
| Stock-local `1180px` / `700px` rules | Directory columns and compact stock presentation adapt independently of the shell. |
| Detail-local `1550px` / `1180px` / `960px` / `600px` rules | The reading sidebar is 320px on wide screens and 250px at 1180px; below 960px the main layout becomes one column, followed by compact detail refinements at 600px. |

Detail-specific responsive refinements are kept in `details.css`; use those selectors when extending detail pages rather than copying the shell's layout assumptions. The app's minimum viewport width is 320px. On mobile, search results become a fixed panel below the header, horizontally overflowing tab/filter rows can scroll, and toast placement clears bottom navigation.

Depth comes mainly from dark surface changes and fine borders. The SVG map uses faint cluster boundaries, individual document nodes and supplied relationship edges. Its layout is fixed after d3-force calculation and cached by identity. Search results and feedback can use shadows, including the toast's `0 8px 24px #0006`. Common panels use 12px corners and 24px padding (20px padding on mobile); buttons use 6px corners, chips and icon buttons 5px, and map containers 12px/10px at desktop/mobile. The map has a dedicated [snapshot/graph contract and handoff](../../docs/frontend/PULSE_MAP.md).

## Component ownership and reuse

| Owner | Responsibility and extension point |
|---|---|
| `app/` | App composition, hash routing, shell layout and render boundary |
| `features/` | Shared bookmarks and asynchronous global search |
| `pages/` | Page-owned views, charts/filter state and local discussion |
| `components/` | Shared event/entity displays, chart and generic UI |
| `data/` | Async read interfaces, mock/API adapters, page loaders and fixture data |
| `lib/format.js` | Pure display formatting |

Common controls use CSS classes rather than a separate button library. `.wp-button` supports default, `data-variant="primary"` and `data-variant="ghost"`; primary uses teal with dark text. Default buttons have a 39px minimum height, rising to 43px on mobile. `.wp-chip` uses `data-active` for its selected treatment; interactive chips should retain the corresponding accessible state used by their owner. `.wp-icon-button` uses `aria-pressed` or `data-active` for saved emphasis. Common controls have hover styling and a 2px gold focus outline with 4px offset. Disabled controls reduce opacity and disable pointer actions through native button state.

`TrendChart` accepts `data`, `valueKey`, `label`, `color`, `baseline` and `height`. It measures its container with `ResizeObserver`, exposes a date/value readout, and supports an optional dashed baseline. Price mode enlarges the vertical scale and explicitly labels that behavior. `ArticleNetwork` renders illustrative relationships plus external Wikipedia links or selection buttons; the companion controls carry navigation, not the drawn edges. `EmptyState` accepts a title, description and action for no matches, missing records or recovery.

## Mock storage and integration boundary

The shell owns `savedEvents` and `savedStocks` and passes callbacks to pages. Browser storage keys are `wikipulse.savedEvents` and `wikipulse.savedStocks`, each containing a JSON array of fixture identifiers. Reads tolerate malformed JSON and remove duplicate or malformed IDs. Unknown IDs remain stored; only confirmed 404 records are omitted from the saved view. Writes update React state immediately; a storage exception produces a message explaining that the selection will be lost on refresh. A normal toast clears after 3.5 seconds. Saving does not create an account, synchronize devices or call an API.

Pages consume a scoped data context loaded asynchronously through the selected mock/API client. Global search calls the common asynchronous search interface after 250ms, matching event titles/keywords, document names/titles and stock names/symbols with at most seven results. Document results are omitted from page navigation. List filters, sorting and chart ranges remain local computations over loaded data. Map node positions and document edges are illustrative layouts. News links are topic references; their existence does not authenticate the synthetic news titles or summaries. Revision text/editor labels, generated summaries, stock paths, scores and prices remain examples even where they refer to real-world topics.

Keep the visible demo disclosures and contextual example labels when changing fixture content. The API adapter implements the proposed read contract, loading/error states, cancellation and manual retry. This does not establish real backend availability. See [data switching](../../docs/frontend/DATA_SOURCE.md).

### Event discussion

Each event starts with three synthetic threads attributed to `리서처 A/B/C`, with example like counts of 4/2/1 and one example reply on the first thread. These are defined in `EventDiscussion.jsx`, separately from `data/mock/fixtures/catalog.js`. The board labels examples and locally written content distinctly and states that nothing is sent to other users. New posts and replies use the fixed display name `나 (데모)` and the browser's current ISO timestamp, not the fixture snapshot date.

Users can submit a thread, open/close its replies, submit a reply, toggle a thread like, and choose latest or most-liked ordering. Latest sorts by descending creation time; most-liked sorts by descending likes, then creation time. Replies retain append order. New threads return the list to latest ordering. Text is rendered as React text with preserved line breaks. Forms trim leading/trailing whitespace, reject empty content and limit text to 1,000 JavaScript string-length units; internal spaces remain. The event limit is 200 threads including examples, and each thread supports at most 200 replies. Reply likes, nested replies, editing, deletion, reporting and discussion search are not implemented.

Each event uses the storage key `wikipulse.discussion.${event.id}` with this local JSON shape:

```js
{
  version: 1,
  threads: [{
    id, author, body, createdAt, isOwn, isSeed,
    likes, liked,
    replies: [{ id, author, body, createdAt, isOwn, isSeed }]
  }]
}
```

Message IDs and authors must be strings of at most 120 and 80 units; body must be a nonblank string of at most 1,000 units; `createdAt` must parse as a date; ownership/example flags are booleans. Threads additionally require a nonnegative integer like count, boolean `liked`, and a reply array within the limit. Version, arrays and every message are checked when loading. An unreadable or invalid stored record restarts from the example threads with an explanation; it is replaced in storage only when a later mutation succeeds.

Committed changes update React state, browser storage and a module-level per-event cache. The cache keeps submitted content and likes available across tab switches and route remounts during this page session, including when storage writes fail; a warning explains loss after refresh in that case. Draft text, expanded replies and sorting are component state and reset on remount. Storage is read on initialization; there is no cross-tab storage listener or user synchronization. These local flags and the fixed author name establish no authenticated identity. Future discussion request/response schemas are **proposals** in [API_SPEC.md §11](./API_SPEC.md#11-사건-토론-현재-로컬-동작과-향후-계약); the component performs no HTTP requests.

The discussion reuses shared primary buttons and gold focus outlines. Its own CSS provides a dark bordered 9px textarea, divider-separated threads and indented reply lists; at 600px it reduces reply indentation and textarea padding. Thread likes expose `aria-pressed`; reply toggles expose `aria-expanded`/`aria-controls` and collapsed replies use `hidden`. Textareas have explicit labels, the main draft counter is associated through `aria-describedby`, and operation feedback uses a polite status region.

## Accessibility and interaction behavior

Implemented support includes a skip-to-content link, a focusable main region focused after workspace route changes, named navigation landmarks, and explicit navigation labels that survive the tablet icon-only layout. Global search uses combobox/listbox semantics, `Ctrl/Cmd+K`, Up/Down selection, Enter navigation and Escape dismissal. Outside pointer interaction also dismisses results.

Event tabs use tab/tablist/tabpanel roles, roving tab stops and Left/Right/Home/End navigation. Map clusters are focusable buttons with selected state and Enter/Space activation; zoom/reset are named native buttons. Charts expose text labels/readouts and Left/Right date navigation. Revision changes and save feedback use polite live regions. Save actions expose names/state; external reference links include new-tab text where implemented. Reduced-motion CSS removes normal workspace animation and transition duration.

These are implementation behaviors, not a WCAG certification. When extending the UI, preserve keyboard paths, readable state labels and recovery actions alongside visual state. Keep essential values and explanations in DOM text, use links for route changes and buttons for local actions, and keep source references, fixture examples and proposed API behavior distinct.
