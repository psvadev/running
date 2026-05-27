# Puls — Project Handoff

## What this is
A self-contained single-file running tracker web app (`puls.html`) that replaces the user's multi-tab Excel workbook. Norwegian UI throughout.

## File locations
- **App:** `c:\temp\GitHub\running\puls.html`
- **Repo:** `https://github.com/psvadev/running` (private)
- **Data:** wherever the user saves their `puls.json` (opened via File System Access API in Edge/Chrome)

---

## Tech stack
| Concern | Choice |
|---|---|
| Structure | Single `.html` file, no build step, no framework |
| Charts | Chart.js 4.4.0 (CDN) |
| Excel import | SheetJS xlsx 0.18.5 (CDN) |
| Data storage | Local JSON file via File System Access API (Edge/Chrome auto-save); download/upload fallback for Firefox |
| Handle persistence | `HandleDB` — stores `FileSystemFileHandle` in IndexedDB so the file re-attaches on next load without a file picker |
| Language | Vanilla JS, no TypeScript |

---

## Data model (`puls.json`)

> **Note on shoes:** Stored as objects (`{ name, retirementKm?, retired?, startDate? }`). `retired: true` hides the shoe from the session form dropdown but keeps it visible in the log filter and shoe overview. Old files with string arrays are migrated automatically by `Store._migrate()`.


```json
{
  "sessions": [{
    "id": "uuid-style string",
    "dato": "2026-05-24",          // ISO date string
    "uke": "2026-21",              // ISO week e.g. YYYY-WW
    "oktnavn": "Runna easy run",
    "okttype": "Easy",             // Easy | Steady | Long | Tempo | Intervaller | Test
    "treningsplan": "Runna",       // Runna | Egentrening
    "varighet": 3060,              // seconds (auto-summed from zones)
    "distanse": 6.5,               // km
    "gjsnittspuls": 141,           // bpm or null
    "toppuls": 150,                // bpm or null
    "soner": [44, 2842, 167, 0, 0],// seconds per zone 1–5
    "kalorier": 672,               // or null
    "tempo": 470,                  // seconds/km (auto-calculated); displayed as MM:SS
    "snittkmh": 7.7,               // auto-calculated
    "stigning": 1.0,               // % (step 0.5)
    "malDistanse": 8.0,            // optional km target set at logging time; null if not set
    "sko": "ASICS Novablast 5",
    "løpetype": "utendors",        // "utendors" | "treadmill"; default "utendors" (missing = outdoor)
    "sovn": 6.87                   // decimal hours (e.g. 6.87 = 6h52m); display via hoursToHHMM()
  }],
  "shoes": [
    { "name": "ASICS Novablast 5", "retirementKm": 650 },
    { "name": "Saucony Ride 18", "retired": true }
  ],
  "events": [
    { "id": "abc123", "date": "2026-01-15", "title": "Start Runna 10K", "type": "plan",
      "targetKmPerWeek": 15, "targetRunsPerWeek": 3 },
    { "id": "def456", "date": "2026-02-01", "endDate": "2026-02-10", "title": "Forkjølet", "type": "illness" }
  ],
  "goals": {
    "2026": 705                    // yearly km goal; keyed by year string
  },
  "consistencySettings": {
    "kmThreshold": 15,             // km/week threshold for Treningsrytme score
    "runThreshold": 2              // runs/week threshold for Treningsrytme score
  },
  "settings": {
    "maxHR": 195,
    "restHR": 55,
    "zones": [
      {"min": 98, "max": 117},
      {"min": 117, "max": 137},
      {"min": 137, "max": 156},
      {"min": 156, "max": 176},
      {"min": 176, "max": 195}
    ]
  },
  "lastUpdated": "2026-05-24T10:00:00Z"
}
```

---

## App structure (5 tabs)

### ➕ Legg til økt (form tab)
- Fields in **Excel column order**: Dato, Uke (auto), Øktnavn, Økt-type, Treningsplan, Varighet (auto), Distanse, Gj.snittspuls, Toppuls, Sone 1–5, Kalorier, Tempo (auto), Snitt km/t (auto), Stigning, Sko, Søvn
- Layout: 4 sections
  - **Øktinfo** (5-col auto-fill): Dato, Uke, Øktnavn, Økt-type, Treningsplan, Løpetype
  - **Ytelse** (4-col fixed): Varighet, Distanse, Gj.snittspuls, Toppuls
  - **Pulssoner** (5-col zone-grid): Sone 1–5
  - **Trailing row** (4-col, 2 rows): Kalorier, Mål distanse, Tempo, Snitt km/t → Stigning, Sko, Søvn, (empty)
- Auto-calculated (readonly, shown in accent blue): Varighet (sum of zones), Tempo, Snitt km/t
- Løpetype defaults to **Tredemølle** on new/clear sessions
- Stigning: `step="0.5"` — spinner moves in 0.5% increments; **hidden (display:none) when Utendørs is selected** — field and label disappear, value cleared; re-appears when switching back to Tredemølle
- Shoe dropdown has a `+` button that navigates to Innstillinger tab
- Edit mode: clicking a row in the log pre-fills the form; edit banner shown; "Oppdater økt" replaces "Lagre økt"

### 📊 Oversikt (dashboard tab — full width)
- Filter bar at top: økt-type dropdown, treningsplan dropdown, **løpetype radios** (Alle / 🏃 Ute / ⚙️ Inne), year pills (toggle individual years), Nullstill button. Løpetype filter is part of `DashFilter` and affects all charts.
- **Yearly goal card** (full-width, hidden if no goal set): progress bar, km løpt, km igjen, Prognose (year-end projection), km/uke nødvendig. Green if on track, warning if projected to fall short.
- Charts (all **week-based**, not per-session — except Records). **Card order** (top to bottom): Årsmål → Rekorder → **Innsikter** → **Treningsrytme** → PMC → Belastning → Ukentlig distanse + Tempo → **Plan vs faktisk** → Treningskalender → **Ute vs inne** → Årssammenligning → Aerob effektivitet → Pulssoner → **Sko oversikt** + Ukentlig oversikt
  - **Rekorder** — general records (best pace, longest dist/time, best km/h, total dist/time, best week, longest streak) + **Distanse-PR** sub-section (5 km, 10 km, Halvmaraton, Maraton — fastest session per bracket)
  - **Treningsstatus (PMC)** — line chart, last 365 days; three lines: Kondisjon/CTL (42-day exp. avg, blue), Tretthet/ATL (7-day exp. avg, red), Form/TSB (CTL−ATL, green). Always uses `allSessions` regardless of dashboard filter — CTL/ATL require full history to be meaningful (full-width)
  - **Treningsbelastning per uke** — bar chart, weekly load score (zone minutes × zone weight Z1=1…Z5=5); bars color-coded green/amber/red relative to personal max; blue 4-week rolling average line overlay (full-width). Supports event marker lines. **Tooltip shows:** load points + level + km/løp/tid. **Click a bar → `DetailPanel.openWeek`**.
  - **Ukentlig distanse** — bar chart, km per week (last 20 weeks). Supports event marker lines. Uses `_rawLabels` (YYYY-WW) for event matching. **Tooltip shows:** week label, km, løp, tid, tempo, HR. **Click a bar → `DetailPanel.openWeek`**.
  - **Tempo per uke** — line chart, weighted average pace per week (total time ÷ total km). Supports event marker lines. **Tooltip shows:** pace + km/løp/tid. **Click a point → `DetailPanel.openWeek`**. Uses `_rawLabels` (YYYY-WW) for event matching.
  - **Plan vs faktisk** — bar chart, last 20 weeks where ≥1 session has `malDistanse` set; **hidden when no sessions have a target**. Bars coloured by completion %: blue ≥105%, green ≥100%, amber ≥80%, red <80%. Dashed white line shows the target km per week. Tooltip shows % av mål. Aggregates all session targets within a week (e.g. Mon 5 km + Wed 8 km = 13 km target for the week).
  - **Treningskalender** — GitHub-style heatmap calendar (full-width). Four modes toggled via radio: *Distanse* (blue intensity by quartile), *Belastning* (zone-weighted load by quartile), *Økttype* (cell coloured by dominant session type), *Pulssone* (cell coloured by dominant HR zone: green Z1 → red Z5). **Second radio row** (Alle / Utendørs / Tredemølle) scopes the heatmap to a venue without affecting other charts. **Custom styled tooltip** replaces native `title` — appears immediately on hover with date, km, type, and session names (multi-line, `white-space:pre-line`). **Click a day cell** → single session: opens `DetailPanel.openSession`; multiple sessions on same day: opens `DetailPanel.openWeek` for that ISO week. **Stats bar** below calendar: Aktive dager, Totalt km, Nåværende streak, Lengste streak (computed for the visible period). Shows last 52 weeks; if single year selected, shows full calendar year. Type and zone modes include a colour legend. **Cell size is dynamic** — calculated from `container.offsetWidth` to fill the card width (min 10px). **Day labels** M T O T F L S are aligned to their row (label column uses matching height + gap; `margin-right:4px` separates labels from cells). **Radio buttons call `renderHeatmap()` directly** — they do not trigger a full `renderDashboard()` re-render.
  - **Ute vs inne** — stacked bar chart (full-width), last 20 weeks, 🏃 outdoor km (green) + ⚙️ treadmill km (blue). **Hidden when no treadmill sessions exist** (card id: `venueCard`). Responds to DashFilter.
  - **Årssammenligning** — cumulative km by week number, one line per year (full-width); **hidden when exactly one year is selected** (card id: `yearCompCard`); responds to type/plan filters
  - **Aerob effektivitet (Easy-økter)** — line chart; per-session score = `snittkmh / gjsnittspuls × 100` for Easy sessions only; **treadmill sessions auto-excluded** (treadmill pace is machine-controlled, not effort-based); individual points + 4-session rolling average (green) + personal average reference line (dashed amber). Tooltip shows session name, speed, and HR. Responds to dashboard filter
  - **Pulssoner** — stacked bar, time per zone per week, last 20 weeks; Y-axis and tooltips display in `tt:mm` (h:mm) format via `minsToHm()`; **Uke/Måned toggle** switches grouping
  - **Treningsrytme** — consistency score card (span2, after Innsikter). Score 0–100 from 3 components: active-week rate (×50), volume consistency weeks above km threshold (×30), current streak bonus (×20, maxes at 4+ weeks). Labels: Svært jevn rytme (≥85) / God rytme (≥70) / Jevn (≥55) / Litt ujevn (≥40) / Ujevn trening (<40). 4 stat tiles: aktive uker, uker over km-grense, uker med N+ løp, nåværende streak. Bar chart below: active weeks per month, last 12 months. Thresholds (km-grense, løp-grense) configured in ⚙️ Innstillinger → Treningsrytme; persisted as `consistencySettings` in JSON. Card id: `rhythmCard`.
  - **Treningsblokker** — training block cards (span2, after Treningsrytme); **hidden when no Plan events exist**. Auto-generated from events with `type: "plan"`: each Plan event starts a block that runs until the next Plan event start, or the event's own `endDate` if set, or today for the current block. **Active block** (endDate ≥ today) renders as a full-width hero card: accent-coloured border, 16px/700 title, full metrics row, consistency progress bar with colour-coded label (Fremragende ≥85 / God konsistens ≥70 / Moderat ≥50 / Ujevn <50), and a pure-SVG weekly km sparkline. **Past blocks** render as compact cards below (4px consistency bar, no sparkline). Newest block first. Click opens DetailPanel (`openBlock`). Card id: `blocksCard`.
  - **Innsikter** — auto-generated insight tiles (span2, after Rekorder). Up to 6 tiles, each with icon + bold value + muted sub-label. Generators: km-milepæl (total distance passed a round number), mest brukte sko (by km), tyngste 4-ukers blokk (rolling zone-weighted load, labelled `S1=1 → S5=5 pkt/min`), raskeste Easy-økt (best pace on Easy sessions), mest aktive måned (session count). Responds to DashFilter. Streak and best-week tiles intentionally omitted — both already shown in Rekorder.
  - **Sko oversikt** — horizontal bar per shoe showing total km + ⚠️/🔴 retirement warning. Below each bar: chip row with `X løp`, `X:XX /km` (avg pace), `HR X` (avg HR, omitted if no HR data), `sist DD.MM.YYYY` (last run date). **Clicking any shoe bar opens `DetailPanel.openShoe`** with full stats + recent sessions. Shoes separated by subtle divider lines.
  - Weekly summary table (scrollable)

### 📋 Treningslogg (log tab — full width)
- Full-width sortable table (click column headers); columns include **Plan** (treningsplan) after Navn and **Mål km** after Dist
- Filters: fra/til dato, økt-type, **treningsplan (Plan)**, **løpetype** (Alle / 🏃 Utendørs / ⚙️ Tredemølle), sko — all wired to `fFilterPlan`, `fFilterLopetype` etc.; Nullstill clears all
- Each row shows a 🏃/⚙️ venue badge next to the session type badge (all sessions; untagged = outdoor)
- Row actions: ✏️ edit (goes to form tab, **returns to log on save/cancel**), 🗑️ delete (with confirm)
- **"Importer Excel/CSV"** button → SheetJS modal with preview before confirming

### 📅 Planlegging (planning tab — max 1200px)
- **Mål**: add yearly km goals (year + km); listed with delete button (with confirm); triggers goal card on dashboard
- **Sko**: add by name + optional retirement km. Shows progress bar + projected retirement date (8/12-week rate). Old string-only JSON files migrated automatically. **Pensjonér** button marks a shoe as retired (hidden from session form dropdown, grayed out with 📦 icon in Settings, still visible in log filter for historical searches). **Aktiver** restores a retired shoe. Retired shoes appear below a "Pensjonerte sko" divider. **Fjern** permanently deletes with confirm.
- **Hendelser**: add timeline events (start date, optional end date, type, title). Types: **plan / race / illness / vacation / personal**. When type = **plan**, two optional extra inputs appear: *Mål km/uke* and *Mål løp/uke* — saved as `targetKmPerWeek` and `targetRunsPerWeek` on the event object. These targets are used in the Treningsblokker detail panel to show "X/N uker over target". Point events = dashed vertical line; range events (with `endDate`) = semi-transparent shaded band with dashed borders. Toggled via "Hendelser" checkbox in dashboard filter bar. Delete has confirm dialog. Event list shows date range as "DD. MMM – DD. MMM" when endDate present.

### ⚙️ Innstillinger (settings tab — max 1200px)
- **Profil & Puls**: max HR, resting HR, 5 zone BPM boundaries, "Auto-beregn" button (fills zones at 50/60/70/80/90% of max HR)
- **Treningsrytme**: km-grense per uke (default 15) and løp-grense per uke (default 2); saved to `Store.data.consistencySettings`; triggers `renderDashboard()` on save so score updates immediately
- **Datafil**: open file, new file, download/export, **📥 Importer Excel/CSV** (moved here from Treningslogg), "Tøm alle data" danger button

---

## Header
- **💾 Lagre** button: always-visible manual save (calls `FileIO.save()`)
- File status indicator and sync dot (auto-save status)

---

## Key JS objects / functions

| Name | Role |
|---|---|
| `Store` | In-memory data; `addSession`, `updateSession`, `deleteSession`, `mergeSessions`, `_migrate()` |
| `HandleDB` | IndexedDB wrapper; `get()`, `set(handle)`, `clear()` — persists `FileSystemFileHandle` across page loads |
| `FileIO` | File System Access API wrapper; `open()`, `save()`, `download()`, `loadCache()`, `restoreHandle()` |
| `Form` | Form read/write; `read()`, `populate()`, `save()`, `editSession()`, `autoCalcVarighet()`, `autoCalcPace()`. `editSession()` stores `returnTab` so save/cancel navigates back to the originating tab. |
| `Log` | Session table render + sort/filter |
| `DashFilter` | Dashboard filter state (years Set, type, plan, løpetype); `get(sessions)` returns filtered array |
| `Settings` | Shoe management, goal management, zone editor, profile save, file controls |
| `Import` | SheetJS parse, Norwegian column mapping, preview modal, `mergeSessions` dedup |
| `renderDashboard()` | Rebuilds all chart panels and goal card; calls `buildYearPills()`, `renderInsights()`; hides `yearCompCard` when single year selected |
| `renderInsights(sessions)` | Generates up to 6 auto-insight tiles into `#insightContent`. Each tile: `{ icon, val, sub }`. Generators: km milestone, most-used shoe, highest 4-week load block, fastest Easy pace, most active month. |
| `renderConsistency(sessions)` | Renders the Treningsrytme card: computes score (0–100) from active-week rate (×50), volume consistency (×30), and streak bonus (×20) over last 12 weeks; reads thresholds from `Store.data.consistencySettings`; renders stat tiles, three score-breakdown progress bars (showing pts earned vs max for each component), and monthly active-weeks bar chart into `#rhythmCard`. |
| `computeBlocks(allSessions)` | Pure function: filters Plan events, maps each to a block object with full analytics (km, runs, pace, HR, consistency %, indoor/outdoor split, shoes, target tracking, `weeklyKm` array for sparkline). Block range = event.date → next Plan event start / event.endDate / today. Returns `[]` when no Plan events exist. |
| `renderBlocks()` | Renders the Treningsblokker card (`#blocksCard`) using `Store.data.sessions` (always unfiltered). Hides card when `computeBlocks` returns empty. Splits blocks into current (hero card) and past (compact cards). Each card click passes the block via `data-block` attribute + `JSON.parse` to `DetailPanel.openBlock`. |
| `blockSparkline(weeklyKm)` | Pure SVG sparkline (no Chart.js). Accepts ordered array of weekly km values; returns inline `<svg>` string with a filled area + polyline. Returns `''` when fewer than 2 data points. |
| `consistencyMeta(score)` | Returns `{ label, color }` for a consistency score: ≥85 Fremragende (green), ≥70 God konsistens (lime), ≥50 Moderat (amber), <50 Ujevn (red). Used in hero card and compact past cards. |
| `DetailPanel` | Reusable drill-down modal object. Methods: `open(title, html)`, `close()`, `openWeek(isoWk, allSessions)`, `openSession(id)`, `openShoe(name)`, `openBlock(block)`. Uses `#detailModal` (`.modal-backdrop`, `max-width:800px`, `max-height:92vh`, thin styled scrollbar). Closed by ESC key or ✕ button. `openBlock` re-derives session data from `Store.data.sessions` at open time (not from serialised block) and renders 7 sections: overview stats (km/løp/tid/km-per-uke/tempo/HR), **Ukentlig progresjon** (per-week bar chart with km + run count + pace, best week highlighted; each row is clickable → `openWeek`; badges Toppuke/Lengste løp/Raskest shown below the row when earned), **Høydepunkter** (auto-generated bullets: best week [links to openWeek], longest run [links to openSession], streak ≥3 weeks, pace trend if ≥4 pace weeks), **Konsistens** (score bar + label + active-weeks breakdown + streak + optional target lines), **Sammenlignet med [prev block]** (colored ± for distanse/km-per-uke/tempo/konsistens, shown only when a previous block exists), **Detaljer** (shoes + indoor/outdoor split, omitted when all-outdoor), **Løp i blokken** (all sessions newest-first, each row clickable to `openSession`). |
| `renderPMCChart(allSessions)` | PMC chart — walks every calendar day from first session to today, accumulating CTL and ATL via exponential decay; displays last 365 days. Always called with `allSessions` (not filtered). |
| `renderEfficiencyChart(sessions, venueFilter)` | Aerobic efficiency chart — filters to Easy sessions with HR data; `snittkmh` derived on-the-fly from `distanse/varighet` if not stored (fixes imported sessions missing the field); `venueFilter` ('all'/'outdoor'/'indoor') controlled by **Alle/Utendørs/Tredemølle** toggle pills (state: `aeVenueFilter`, default 'all'); computes score = `snittkmh/gjsnittspuls×100`; renders points + 4-session rolling avg + personal average reference line; shows explanatory message when fewer than 2 sessions qualify. |
| `renderVenueChart(sessions)` | Stacked bar chart (last 20 weeks): outdoor km (green) vs treadmill km (blue). Hidden when no treadmill sessions. |
| `renderHeatmap(sessions)` | Training calendar heatmap — GitHub-style grid, 4 modes: distance (blue intensity), belastning (zone-load intensity), økttype (coloured by dominant type), pulssone (coloured by dominant HR zone). `dailyData` entries carry `zones:[0,0,0,0,0]` and `ids:[]` for zone mode and click navigation. Click handler registered once in `DOMContentLoaded` via delegation on `#heatmapContainer` → single session: `DetailPanel.openSession`; multiple sessions same day: `DetailPanel.openWeek`. Custom tooltip registered the same way. Stats bar (`#heatmapStats`) shows active days, total km, current/longest streak for the visible period. Uses DashFilter year for range. Reads `input[name="heatmetric"]` radio for mode. |
| `eventLinesPlugin` | Chart.js globally registered plugin (`Chart.register(eventLinesPlugin)`). Runs on ALL charts. Draws dashed vertical lines (point events) or semi-transparent shaded bands with dashed borders (range events with `endDate`). Safely no-ops on charts where labels don't match. Guarded with double try-catch so errors never crash chart rendering. |
| `computeRecords(sessions)` | Returns general records + `distPRs` array (5k/10k/halvmaraton/maraton — fastest session per distance bracket). Streak uses Monday-aligned epoch week index for correct ISO week / year-boundary handling. |
| `renderZoneChart(sessions)` | Standalone function; reads `zoneGroupBy` ('week'/'month') to group data |
| `fmtWeekLabel(wk)` | Formats a `YYYY-WW` string as `"Uke N 'YY"` — used for all weekly chart display labels; defined near `isoWeek` |
| `malCell(s)` | Returns colour-coded HTML for the log table "Mål km" cell; blue ≥105%, green ≥100%, amber ≥80%, red <80% of target; empty string if `malDistanse` is null |
| `minsToHm(m)` | Formats decimal minutes as `h:mm` (e.g. `90.5` → `"1:30"`); used in Pulssoner chart ticks and tooltips |
| `refreshAll()` | Called after any data change; re-renders log, shoe list, dashboard if visible |
| `switchTab(name)` | Tab navigation; triggers tab-specific render (`dash`→`renderDashboard`, `log`→`Log.render`, `plan`/`settings`→`Settings.render`) |

Global state:
- `let zoneGroupBy = 'week'` — controls Uke/Måned toggle for zones chart
- `let aeVenueFilter = 'all'` — controls Alle/Utendørs/Tredemølle toggle for aerobic efficiency chart

---

## Important quirks & fixes made during build

### File handle persistence (HandleDB)
- `FileIO.restoreHandle()` is called on startup after `loadCache()`
- `queryPermission({ mode:'readwrite' })` — if `'granted'` (same session/recent reload): reads file silently
- If `'prompt'`: status bar shows "📂 Klikk for å gjenåpne [filename]" — one click calls `requestPermission` (requires user gesture)
- If `'denied'` or no handle stored: falls back to cache message
- Handle is stored to IndexedDB in `open()` and on first successful `save()`
- `openNew()` clears the stored handle via `HandleDB.clear()`

### Manual save (💾 Lagre) re-using the existing file
- **Problem:** After a page reload, `this.handle` is null until `restoreHandle()` completes. If the user clicks Lagre first, `save()` would call `showSaveFilePicker` and prompt for a location — even though the file is known.
- **Fix:** `save()` checks IndexedDB for a stored handle before falling back to `showSaveFilePicker`. Clicking Lagre IS a user gesture, so `requestPermission` is allowed inline. `this.handle.name` (synchronous) is used for the filename instead of `getFile()`. Filename is cached in `localStorage('lpl_handle_name')` and used in the write-success path to avoid an extra async `getFile()` call on every save.

### Distance PRs (distPRs)
- Brackets: 5 km (4.5–5.5), 10 km (9.0–11.0), Halvmaraton (19.5–22.0), Maraton (40.0–43.5)
- Best = lowest `tempo` (fastest pace) within bracket
- Displayed as `varighet` (HH:MM:SS) with pace + date subtitle
- Shows "–" if no session logged in that bracket

### Training load chart (Treningsbelastning)
- Score per session = `sum(zone_secs[i] × weight[i]) / 60` where weights = [1,2,3,4,5]
- Grouped by week; bar color relative to personal max in displayed window: <40% = green, 40–70% = amber, >70% = red
- Blue line = 4-week rolling average
- Only counts sessions that have HR zone data logged

### Streak calculation
- Uses Monday-aligned epoch week: `Math.floor((date.getTime() + 3*86400000) / (7*86400000))`
- The `+3 days` shift aligns week boundaries to Monday (ISO week start), so a run on Dec 31 and Jan 1 of the following week count as consecutive weeks correctly. The original Thursday-aligned formula (Unix epoch = Thursday) could falsely break streaks at year boundaries.

### Weekly chart fallback for missing `uke`
- All weekly aggregations use `s.uke || isoWeek(s.dato)` so sessions without a stored week string still bucket correctly. This covers sessions from old imports or hand-crafted records.

### søvn (sleep) format
- **Problem:** Excel stores time values (e.g. `6:52`) as fractions of a day (`0.2868`). `parseFloat` took the raw fraction.
- **Fix:** `parseSovn(val)` detects `val > 0 && val < 1` → multiplies by 24 to get decimal hours.
- **Migration:** `Store._migrate()` runs on every `load()` and converts any stored `sovn < 1` values automatically.
- **Storage:** decimal hours (e.g. `6.87`). Display via `hoursToHHMM(h)` → `"6:52"`.

### Excel column mapping (`COL_MAP`)
- The user's Excel has a typo: `"Trenignsplan"` (missing 'a') instead of `"Treningsplan"`. Both are mapped.
- All Norwegian column headers from the user's exact sheet are mapped, including `"Gj.snittspuls"`, `"Sone1 (min)"` etc.
- `parseExcelTime(val)` handles both numeric fractions (Excel internal) and `"H:MM:SS"` strings.
- `parseExcelDate(val)` handles Excel serials, `MM/DD/YYYY`, and ISO strings.

### Shoe data model migration (strings → objects)
- `Store.data.shoes` was originally `string[]`. Now `{ name, retirementKm?, startDate? }[]`.
- `_migrate()` converts old string arrays on load. All code that reads shoe names uses `s.name`.
- Sessions still store `sko: string` (the shoe name), unchanged.

### Event markers — label matching
- Plugin is **globally registered** via `Chart.register(eventLinesPlugin)` so it runs on every chart. Charts without matching labels simply draw nothing.
- Matching order: try `evt.date` exact string first, then `isoWeek(evt.date)` (returns `YYYY-WW`).
- PMC chart uses daily ISO date labels → matches `evt.date` directly.
- Load, weekly dist, and pace charts use formatted display labels (`"Uke 21 '26"`) but all store `_rawLabels` (raw `YYYY-WW`) on `chart.data` → plugin reads `chart.data._rawLabels` first.
- Range events (`endDate` present): draws a `rgba(..., 0.12)` filled rect + dashed start line. End line drawn only when the end label is found. **End-date finding order**: (1) exact match, (2) `isoWeek` match, (3) nearest session-week before the end date (handles gaps where the end week had no sessions). If end is beyond the visible range entirely, band extends to the right edge with no end line.
- Band edges: both dashed lines and the filled rect use the same `xStart = x - colWidth/2` and `xEnd = meta.data[idx2].x + colWidth/2` coordinates — no offset between line and band boundary.

### snittkmh rounding
- **Problem:** Excel imports stored `snittkmh` as the raw float (e.g. `7.664592204389127`).
- **Fix:** Import parser now rounds to 2 decimal places: `+parseFloat(obj.snittkmh).toFixed(2)`. `autoCalcPace()` was also updated from `.toFixed(1)` to `.toFixed(2)`.
- **Migration:** `Store._migrate()` rounds any stored `snittkmh` that differs from its 2-decimal representation, so existing data is cleaned up on next load.

### Auto-calculated fields
- `varighet`, `tempo`, `snittkmh` are `readonly` inputs styled with accent colour and no border.
- They are set programmatically; the form's `clear()` still resets them.

### Goals data
- Stored as `Store.data.goals: { "YYYY": km }` — plain object keyed by year string.
- `_migrate()` ensures `goals` exists on old files that pre-date this feature.
- Dashboard goal card is hidden if no goal is set for the target year.
- Target year = single selected year in filter, otherwise current calendar year.
- Goal card always uses `allSessions` (unfiltered) — intentional, since the yearly km goal is a total regardless of session type.

---

## Roadmap / future plans

### Phase 2 — Google Drive sync
- Replace local JSON with a single `puls.json` in Google Drive
- OAuth 2.0 PKCE flow (no backend needed), `drive.file` scope
- Needs a **new** Google Cloud project (not shared with other apps)
- `FileIO` is designed as a thin wrapper — swap `open()`/`save()` implementations only
- Redirect URI will depend on hosting (see below)

### Phase 3 — Hosting
- **GitHub Pages** for the HTML file (free static hosting)
- **Cloudflare Access** in front for auth (Cloudflare Zero Trust, free tier)
- **Custom domain** via Cloudflare DNS
- No backend needed — the app is entirely client-side

### Other ideas noted
- HR zone labels in charts could show actual BPM ranges once settings are saved
- Import dedup logic: matches on `dato + distanse (±0.05km) + varighet (±30s)`

---

## How to open and test
1. Open `puls.html` in **Edge** or **Chrome**
2. Go to **⚙️ Innstillinger** → click **📂 Åpne fil** → select your `puls.json`
3. Data loads; all tabs refresh automatically
4. On subsequent loads the app will attempt to reattach the file handle automatically
5. In **Firefox**: same, but use "⬇️ Last ned" to save changes (no auto-save)

## Saving a new file (Edge/Chrome)
- Click **✨ Ny fil** → enter some data → click **💾 Lagre** in the header (or save a session)
- Browser shows a "Save As" dialog on the first save; pick folder and filename (default: `puls.json`)
- All future saves are automatic; handle persists across page reloads via IndexedDB

## Re-importing Excel data
- Export the Excel sheet as `.xlsx` or `.csv`
- Go to 📋 Treningslogg → **Importer Excel/CSV**
- Preview shown before confirming; duplicates are skipped automatically
- If re-importing to fix data (e.g. søvn), clear sessions first via Innstillinger → Tøm alle data, then re-import
