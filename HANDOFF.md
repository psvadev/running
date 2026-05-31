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
| Backup persistence | `BackupDB` (`lpl_backups` IndexedDB db) — daily JSON snapshots, last 7 kept; auto-triggered on every `Store.load()` |
| Favicon | Inline SVG data URI in `<head>` — 🏃 emoji, no external file |
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
    "okttype": "Easy",             // Easy | Steady | Long | Tempo | Intervaller | Test | Race
    "treningsplan": "Runna",       // Runna | Egentrening
    "varighet": 3060,              // seconds (auto-summed from zones)
    "distanse": 6.5,               // km
    "gjsnittspuls": 141,           // bpm or null
    "toppuls": 150,                // bpm or null
    "soner": [44, 2842, 167, 0, 0],// seconds per zone 1–5
    "kalorier": 672,               // or null
    "tempo": 470,                  // seconds/km (auto-calculated); displayed as MM:SS
    "snittkmh": 7.7,               // auto-calculated
    "stigning": 1.0,               // % (step 0.5); treadmill incline only
    "hoydeMeter": 320,             // elevation gain in metres; outdoor runs only; null if not logged
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
  "bestEfforts": {
    "400m": null,                 // total seconds for 400m best effort (manual entry from Strava/Runna)
    "1k": 362,                    // total seconds; null if not entered
    "5k": null,
    "10k": null,
    "15k": null,
    "half": null,
    "marathon": null
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
  - **Ytelse** (`form-grid form-grid-4`): Varighet, Distanse, Gj.snittspuls, Toppuls
  - **Pulssoner** (5-col zone-grid): Sone 1–5
  - **Trailing row** (`form-grid form-grid-4`, 2 rows): Kalorier, Mål distanse, Tempo, Snitt km/t → Stigning, Sko, Søvn, (empty)
  - **Mobile (≤600px):** `form-grid-4` drops to 2 columns; `zone-grid` drops to 3 columns
- Auto-calculated (readonly, shown in accent blue): Varighet (sum of zones), Tempo, Snitt km/t
- Løpetype defaults to **Tredemølle** on new/clear sessions
- Stigning: `step="0.5"` — spinner moves in 0.5% increments; **hidden (display:none) when Utendørs is selected** — field and label disappear, value cleared; re-appears when switching back to Tredemølle
- Shoe dropdown has a `+` button that navigates to Innstillinger tab
- Edit mode: clicking a row in the log pre-fills the form; edit banner shown; "Oppdater økt" replaces "Lagre økt"

### 📊 Oversikt (dashboard tab — full width)
- Filter bar at top: økt-type dropdown, treningsplan dropdown, **løpetype radios** (Alle / 🏃 Ute / ⚙️ Inne), **Tempo-enhet radios** (min/km / km/t), year pills (toggle individual years), Nullstill button. **Nullstill resets all filters** including paceUnit radio, venue toggle, all scatter/chart-local type pills, and `zoneGroupBy` (Pulssoner Uke/Måned toggle) back to defaults.
- **Yearly goal card** (full-width, hidden if no goal set): progress bar, km løpt, km igjen, Prognose (year-end projection), km/uke nødvendig. Green if on track, warning if projected to fall short.
- Charts (all **week-based**, not per-session — except Records). **Card order** (top to bottom): Årsmål → Rekorder → **Innsikter** → **Treningsrytme** → PMC → Belastning → Ukentlig distanse + Tempo → **Plan vs faktisk** → Treningskalender → **Ute vs inne** → Årssammenligning → Aerob effektivitet → Pulssoner → **Sko oversikt** + Ukentlig oversikt
  - **Rekorder** — four sub-sections rendered from `computeRecords()` + `computePerfCurve()`: (1) main grid (`recordsGrid`): total dist/time, avg km/week, longest session, best week/month/4-week block, Mest høydemeter, best aerob eff., lowest avg HR, longest + current streak; (2) **Pace** sub-section (`paceRecordsGrid`): Beste tempo, Beste snitt km/t, Beste Easy/Long/Tempo/Test/Race pace — all use "pace" label to avoid "Tempo-tempo" ambiguity; Steady and Intervaller excluded (Steady too similar to Easy; interval session pace is not meaningful); (3) **Distanse-PR** (`distPRGrid`): 5 km, 10 km, Halvmaraton, Maraton — fastest session per distance bracket; (4) **Ytelseskurve** (`perfCurveGrid`): 400 m, 1 km, 5 km, 10 km, 15 km, Halvmaraton, Maraton — priority: manual override from `Store.data.bestEfforts` > actual Test/Race session in ±10% range > Riegel estimate (`t2 = t1 × (d/d1)^1.06`) from closest Test/Race anchor ≥1 km; 400m never gets a Riegel estimate; estimated tiles styled with `.record-value.estimated` (muted colour). `computeRecords()` returns `bestEasyPace`, `bestLangturPace`, `bestTempoPace`, `bestTestPace`, `bestRacePace`, `bestHoyde`.
  - **Treningsstatus (PMC)** — line chart, last 365 days; three lines: Kondisjon/CTL (42-day exp. avg, blue), Tretthet/ATL (7-day exp. avg, red), Form/TSB (CTL−ATL, green). Always uses `allSessions` regardless of dashboard filter — CTL/ATL require full history to be meaningful (full-width)
  - **Treningsbelastning per uke** — bar chart, weekly load score (zone minutes × zone weight Z1=1…Z5=5); bars color-coded green/amber/red relative to personal max; blue 4-week rolling average line overlay (full-width). Supports event marker lines. **Tooltip shows:** load points + level + km/løp/tid. **Click a bar → `DetailPanel.openWeek`**. Shows "Ingen data å vise" empty state when no sessions have HR zone data.
  - **Ukentlig distanse** — bar chart, km per week (last 20 weeks). Shows "Ingen data å vise" empty state when filtered to zero sessions. Supports event marker lines. Uses `_rawLabels` (YYYY-WW) for event matching. **Tooltip shows:** week label, km, løp, tid, tempo, HR. **Click a bar → `DetailPanel.openWeek`**.
  - **Tempo per uke** — line chart, weighted average pace per week (total time ÷ total km). Shows "Ingen data å vise" empty state when filtered to zero sessions with pace data. Respects global `paceUnit` toggle (min/km ↔ km/t); Y-axis inverted in pace mode, normal in km/h mode. Supports event marker lines. **Tooltip shows:** pace/speed + km/løp/tid. **Click a point → `DetailPanel.openWeek`**. Uses `_rawLabels` (YYYY-WW) for event matching.
  - **Plan vs faktisk** — bar chart, last 20 weeks where ≥1 session has `malDistanse` set; **hidden when no sessions have a target**. Bars coloured by completion %: blue ≥105%, green ≥100%, amber ≥80%, red <80%. Dashed white line shows the target km per week. Tooltip shows % av mål. Aggregates all session targets within a week (e.g. Mon 5 km + Wed 8 km = 13 km target for the week).
  - **Treningskalender** — GitHub-style heatmap calendar (full-width). Four modes toggled via radio: *Distanse* (blue intensity by quartile), *Belastning* (zone-weighted load by quartile), *Økttype* (cell coloured by dominant session type), *Pulssone* (cell coloured by dominant HR zone: green Z1 → red Z5). **Second radio row** (Alle / Utendørs / Tredemølle) scopes the heatmap to a venue without affecting other charts. Radio button rows use `flex-wrap: wrap` so they reflow on narrow screens. `#heatmapContainer` has `overflow-x: auto` so the calendar scrolls within its card rather than pushing the page width. **Custom styled tooltip** replaces native `title` — appears immediately on hover with date, km, type, and session names (multi-line, `white-space:pre-line`). **Click a day cell** → single session: opens `DetailPanel.openSession`; multiple sessions on same day: opens `DetailPanel.openWeek` for that ISO week. **Stats bar** below calendar: Aktive dager, Totalt km, Nåværende streak, Lengste streak (computed for the visible period). Shows last 52 weeks; if single year selected, shows full calendar year. Type and zone modes include a colour legend. **Cell size is dynamic** — calculated from `container.offsetWidth` to fill the card width (min 10px). **Day labels** M T O T F L S are aligned to their row (label column uses matching height + gap; `margin-right:4px` separates labels from cells). **Radio buttons call `renderHeatmap()` directly** — they do not trigger a full `renderDashboard()` re-render.
  - **Ute vs inne** — stacked bar chart (full-width), last 20 weeks, 🏃 outdoor km (green) + ⚙️ treadmill km (blue). **Hidden when no treadmill sessions exist** (card id: `venueCard`). Responds to DashFilter.
  - **Årssammenligning** — cumulative km by week number, one line per year (full-width); **hidden when exactly one year is selected** (card id: `yearCompCard`); responds to type/plan filters
  - **Aerob effektivitet (Easy-økter)** — line chart; per-session score = `snittkmh / gjsnittspuls × 100` for Easy sessions only; **treadmill sessions auto-excluded** (treadmill pace is machine-controlled, not effort-based); individual points + 4-session rolling average (green) + personal average reference line (dashed amber). Tooltip shows session name, speed, and HR. Responds to dashboard filter
  - **Pulssoner** — stacked bar, time per zone per week, last 20 weeks; Y-axis and tooltips display in `tt:mm` (h:mm) format via `minsToHm()`; **Uke/Måned toggle** switches grouping
  - **Treningsrytme** — consistency score card (span2, after Innsikter). Score 0–100 from 3 components: active-week rate (×50), volume consistency weeks above km threshold (×30), current streak bonus (×20, maxes at 4+ weeks). Labels: Svært jevn rytme (≥85) / God rytme (≥70) / Jevn (≥55) / Litt ujevn (≥40) / Ujevn trening (<40). 4 stat tiles: aktive uker, uker over km-grense, uker med N+ løp, nåværende streak. Bar chart below: active weeks per month, last 12 months. Thresholds (km-grense, løp-grense) configured in ⚙️ Innstillinger → Treningsrytme; persisted as `consistencySettings` in JSON. Card id: `rhythmCard`.
  - **Treningsblokker** — training block cards (span2, after Treningsrytme); **hidden when no Plan events exist**. Auto-generated from events with `type: "plan"`: each Plan event starts a block that runs until the next Plan event start, or the event's own `endDate` if set, or today for the current block. **Active block** (endDate ≥ today) renders as a full-width hero card: accent-coloured border, 16px/700 title, full metrics row, consistency progress bar with colour-coded label (Fremragende ≥85 / God konsistens ≥70 / Moderat ≥50 / Ujevn <50), and a pure-SVG weekly km sparkline. **Past blocks** render as compact cards below (4px consistency bar, no sparkline). Newest block first. Click opens DetailPanel (`openBlock`). Card id: `blocksCard`.
  - **Innsikter** — auto-generated insight tiles (span2, after Rekorder). Up to 6 tiles, each with icon + bold value + muted sub-label. Generators: km-milepæl (total distance passed a round number), next km-milepæl, mest brukte sko (by km), sko nærmer seg pensjonering, tyngste 4-ukers blokk (rolling zone-weighted load), raskeste Easy-økt, mest aktive måned (by km + by count if different), Easy-tempo trend (last 8 vs prior 8 weeks, ≥3% change), Easy HR trend (last 8 vs prior 8 weeks, ≥3 bpm change), Easy Zone 2 compliance, volum trend (last 4 vs prior 4 weeks, ≥10% change), langtursøkt-gap (≥3 weeks since last Long session), høydemeter denne måneden (≥500m), **race countdown** (days until next race event from `Store.data.events` — priority 5 ≤14 days, 4 ≤60 days, 3 otherwise), days since last run (≥10 days). Responds to DashFilter. Streak and best-week tiles intentionally omitted — both already shown in Rekorder.
  - **Sko oversikt** — horizontal bar per shoe showing total km + ⚠️/🔴 retirement warning. Below each bar: chip row with `X løp`, `X:XX /km` (avg pace), `HR X` (avg HR, omitted if no HR data), `sist DD.MM.YYYY` (last run date). **Clicking any shoe bar opens `DetailPanel.openShoe`** with full stats + recent sessions. Shoes separated by subtle divider lines.
  - Weekly summary table (scrollable)

### 📋 Treningslogg (log tab — full width)
- Full-width sortable table (click column headers); columns include **Plan** (treningsplan) after Navn and **Mål km** after Dist
- **Søvn column** colour-coded: red `< 6h`, yellow `6–7h`, green `≥ 7h`; empty cells unstyled
- **Høyde column** — shows `hoydeMeter + 'm'` for outdoor runs and `stigning + '%'` for treadmill runs; blank if neither is set
- **Kal (calories) column removed** — still logged in the form and included in TSV export and session detail panel; just not shown in the table
- **Mobile (≤600px):** 9 secondary columns hidden via CSS `nth-child` — Uke (3), Navn (5), Plan (6), Mål km (8), Varighet (9), ♥ Topp (12), Sko (13), Søvn (14), Høyde (15). Visible: checkbox, Dato, Type, Dist, Tempo, ♥ Snitt, actions. All fields accessible via edit form.
- Filters: fra/til dato, økt-type, **treningsplan (Plan)**, **løpetype** (Alle / 🏃 Utendørs / ⚙️ Tredemølle), sko — all wired to `fFilterPlan`, `fFilterLopetype` etc.; Nullstill clears all
- Each row shows a 🏃/⚙️ venue badge next to the session type badge (all sessions; untagged = outdoor)
- Row actions: ✏️ edit (goes to form tab, **returns to log on save/cancel**), 🗑️ delete (with confirm)
- **Export toolbar** (above the table):
  - **Kopier valgte (N)** — checkbox column on each row; button enables when ≥1 row checked; copies tab-separated table (header + selected rows) to clipboard; shows "Kopiert!" feedback for 1.8 s
  - **Kopier alle filtrerte** — copies all currently visible rows (respecting all active filters) to clipboard
  - **Last ned TSV** — downloads all currently filtered rows as `løpelogg.tsv`
  - Select-all checkbox in header toggles all visible rows; unchecking any row desyncs the select-all
  - Checkboxes and button state reset automatically on every filter change / re-render
  - TSV format matches the original Excel export: 20 columns, Dato as `M/D/YYYY`, Uke as `YYYY-WW`, durations as `H:MM:SS`, zones as `H:MM:SS`, pace as `MM:SS`, sleep as `H:MM`, decimals as dot
- **"Importer Excel/CSV"** button → SheetJS modal with preview before confirming

### 📅 Planlegging (planning tab — max 1200px)
- **Mål**: add yearly km goals (year + km); listed with delete button (with confirm); triggers goal card on dashboard
- **Sko**: add by name + optional retirement km. Shows progress bar + projected retirement date (8/12-week rate). Old string-only JSON files migrated automatically. **Pensjonér** button marks a shoe as retired (hidden from session form dropdown, grayed out with 📦 icon in Settings, still visible in log filter for historical searches). **Aktiver** restores a retired shoe. Retired shoes appear below a "Pensjonerte sko" divider. **Fjern** permanently deletes with confirm.
- **Hendelser**: add timeline events (start date, optional end date, type, title). Types: **plan / race / illness / vacation / personal**. When type = **plan**, two optional extra inputs appear: *Mål km/uke* and *Mål løp/uke* — saved as `targetKmPerWeek` and `targetRunsPerWeek` on the event object. These targets are used in the Treningsblokker detail panel to show "X/N uker over target". Point events = dashed vertical line; range events (with `endDate`) = semi-transparent shaded band with dashed borders. Race events show 🏁 prefix in chart marker labels. Toggled via "Hendelser" checkbox in dashboard filter bar. Delete has confirm dialog. Event list shows date range as "DD. MMM – DD. MMM" when endDate present.
- **Løp & Races**: card below Hendelser listing all `type:'race'` events newest-first. Each row shows race title, date, "Kommende" badge for future races, and matched session stats (distance, time, pace, HR). Session matching: prefers `okttype === 'Race'` session on same date, falls back to longest session within ±1 day. "Ingen økt logget" shown for past races with no match. Refreshes on add/delete event.

### ⚙️ Innstillinger (settings tab — max 1200px)
- **Profil & Puls**: max HR, resting HR, 5 zone BPM boundaries, "Auto-beregn" button (fills zones at 50/60/70/80/90% of max HR)
- **Beste innsats**: manual entry of GPS-derived best effort times (400 m, 1 km, 5 km, 10 km, 15 km, halvmaraton, maraton) from Strava/Runna; format mm:ss or h:mm:ss; saved to `Store.data.bestEfforts` (total seconds per distance key: `'400m'`/`'1k'`/`'5k'`/`'10k'`/`'15k'`/`'half'`/`'marathon'`); overrides Riegel estimates in Ytelseskurve; Lagre triggers `renderDashboard()`
- **Treningsrytme**: km-grense per uke (default 15) and løp-grense per uke (default 2); saved to `Store.data.consistencySettings`; triggers `renderDashboard()` on save so score updates immediately
- **Datafil**: open file, new file, download/export, **📥 Importer Excel/CSV** (moved here from Treningslogg), "Tøm alle data" danger button. **Lokale sikkerhetskopier** card below: lists last 7 daily IndexedDB snapshots (date + session count); **↩ Gjenopprett** restores that backup, overwrites current data, saves the file, and re-renders the backup list in-place; list populated by `Settings.renderBackupList()` which is called on every Settings tab open

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
| `BackupDB` | IndexedDB wrapper (`lpl_backups` db); `save(json, count)`, `getAll()`, `restore(date)` — daily snapshots, last 7 kept; hooked into `Store.load()` |
| `FileIO` | File System Access API wrapper; `open()`, `save()`, `download()`, `loadCache()`, `restoreHandle()`. `save()` always writes to localStorage cache and triggers `DriveIO.save()` when signed in; the entire local-file block (handle recovery + picker) is skipped when Drive is connected so no browser permission dialogs appear. |
| `Form` | Form read/write; `read()`, `populate()`, `save()`, `editSession()`, `autoCalcVarighet()`, `autoCalcPace()`. `editSession()` stores `returnTab` so save/cancel navigates back to the originating tab. |
| `Log` | Session table render + sort/filter; `lastFiltered` holds the current filtered+sorted session array (set on each render; read by export) |
| `LogExport` | Export state object: `selectedIds` (Set of checked session IDs), `update()` (sync button label/enable state), `flash()` (show "Kopiert!" feedback), `getSelected()` (returns sorted sessions for checked IDs) |
| `DashFilter` | Dashboard filter state (years Set, type, plan, løpetype); `get(sessions)` returns filtered array |
| `Settings` | Shoe management, goal management, zone editor, profile save, file controls, best efforts, race history |
| `Import` | SheetJS parse, Norwegian column mapping, preview modal, `mergeSessions` dedup |
| `renderDashboard()` | Rebuilds all chart panels and goal card; calls `buildYearPills()`, `renderInsights()`; computes `cachedBlocks = computeBlocks(Store.data.sessions)` once before calling `renderBlocks()`; hides `yearCompCard` when single year selected |
| `renderInsights(sessions)` | Generates up to 6 auto-insight tiles into `#insightContent`. Each tile: `{ icon, val, sub, priority }`. Generators: km milestone, most-used shoe, highest 4-week load block, fastest Easy pace, most active month, Easy pace trend (last 8 vs prior 8 weeks), days since last run, **Easy run Zone 2 compliance** (🫀 — surfaces only when ≥3 Easy runs with HR exist AND `settings.zones[1]` is configured AND compliance is low; priority 3 when <50%, else 2 so it only shows when actionable). |
| `renderConsistency(sessions)` | Renders the Treningsrytme card: computes score (0–100) from active-week rate (×50), volume consistency (×30), and streak bonus (×20) over last 12 weeks; reads thresholds from `Store.data.consistencySettings`; renders stat tiles, three score-breakdown progress bars (showing pts earned vs max for each component), and monthly active-weeks bar chart into `#rhythmCard`. |
| `computeBlocks(allSessions)` | Pure function: filters Plan events, maps each to a block object with full analytics (km, runs, pace, HR, consistency %, indoor/outdoor split, shoes, target tracking, `weeklyKm` array for sparkline). Block range = event.date → next Plan event start / event.endDate / today. Returns `[]` when no Plan events exist. |
| `renderBlocks()` | Renders the Treningsblokker card (`#blocksCard`) using `cachedBlocks` (set by `renderDashboard` before calling this). Hides card when blocks array is empty. Splits blocks into current (hero card) and past (compact cards). Each card click passes the block via `data-block` attribute (serialized with `toSafeAttr`) + `JSON.parse` to `DetailPanel.openBlock`. |
| `blockSparkline(weeklyKm)` | Pure SVG sparkline (no Chart.js). Accepts ordered array of weekly km values; returns inline `<svg>` string with a filled area + polyline. Returns `''` when fewer than 2 data points. |
| `consistencyMeta(score)` | Returns `{ label, color }` for a consistency score: ≥85 Fremragende (green), ≥70 God konsistens (lime), ≥50 Moderat (amber), <50 Ujevn (red). Used in hero card and compact past cards. |
| `DetailPanel` | Reusable drill-down modal object. Methods: `open(title, html)`, `close()`, `openWeek(isoWk, allSessions)`, `openSession(id)`, `openShoe(name)`, `openBlock(block)`. Uses `#detailModal` (`.modal-backdrop`, `max-width:800px`, `max-height:92vh`, thin styled scrollbar). Closed by ESC key or ✕ button. `openBlock` re-derives session data from `Store.data.sessions` at open time (not from serialised block); `shoes` and `outdoorKm`/`indoorKm` are guarded with `?.` / `\|\|0` to handle degenerate zero-session blocks without throwing. Renders 8 sections: overview stats (km/løp/tid/km-per-uke/tempo/HR), **Ukentlig progresjon** (per-week bar chart with km + run count + pace, best week highlighted; each row is clickable → `openWeek`; badges Toppuke/Lengste løp/Raskest shown below the row when earned), **Høydepunkter** (auto-generated bullets: best week [links to openWeek], longest run [links to openSession], streak ≥3 weeks, pace trend if ≥4 pace weeks), **Konsistens** (score bar + label + active-weeks breakdown + streak + optional target lines), **Sammenlignet med [prev block]** (colored ± for distanse/km-per-uke/tempo/konsistens, shown only when a previous block exists), **Sonefordeling** (stacked colored bar + per-zone % legend + low/high intensity summary using `calcZoneDistribution(blockSessions)`; always shown — graceful fallback text when no zone data logged), **Detaljer** (shoes + indoor/outdoor split, omitted when all-outdoor), **Løp i blokken** (all sessions newest-first, each row clickable to `openSession`). |
| `renderPMCChart(allSessions)` | PMC chart — walks every calendar day from first session to today, accumulating CTL and ATL via exponential decay; displays last 365 days. Always called with `allSessions` (not filtered). Shows empty-state message (`.pmc-empty`) when no sessions have zone data. |
| `renderEfficiencyChart(sessions)` | Aerobic efficiency chart — filters to Easy sessions with HR data; `snittkmh` derived on-the-fly from `distanse/varighet` if not stored (fixes imported sessions missing the field); venue filter read from global `aeVenueFilter` ('all'/'outdoor'/'indoor'), controlled by **Alle/Utendørs/Tredemølle** toggle pills; **Zone 2 filter** read from global `aeZ2Filter` ('all'/'z2') — when 'z2', keeps only sessions where avg HR is within `settings.zones[1]` range OR ≥70% of zone time is in S2; shows included/excluded count in `#aeZ2Count` element; if 'z2' but no zones configured, shows empty-state instead of chart; computes score = `snittkmh/gjsnittspuls×100`; renders points + 4-session rolling avg + personal average reference line; empty-state message reflects active venue filter when fewer than 2 sessions qualify. |
| `renderPaceWeekChart(sessions)` | Weekly pace line chart (last 20 weeks) — builds `paceWeekMap` (weighted dist/secs per week) and renders with `paceUnit`-aware Y-axis (inverted in pace mode, normal in km/h mode); updates `#paceCardTitle` text to match active unit; extracted from `renderDashboard` so the pace unit radio can call it independently without re-rendering the whole dashboard. |
| `renderZ2PaceChart(sessions)` | Zone-2 pace time-series — filters Easy + Langtur sessions (or single type via `z2PaceTypeFilter` toggle: Alle/Easy/Langtur); unit controlled by global `paceUnit` ('pace'=inverted Y with `secsToMmSs` ticks / 'kmh'=normal Y with decimal ticks); 2 datasets: raw values + 4-session rolling average; tooltip adapts label to unit; empty-state when fewer than 2 qualifying sessions. |
| `renderSleepHrChart(sessions)` | Sleep vs HR scatter — X=`sovn` (decimal hours), Y=`gjsnittspuls`; per-type color coding in Alle mode (`sleepHrTypeFilter`); linear regression trend line (dashed gold); legend visible in Alle mode only; tooltip shows type, søvn (H:MM), puls, snittkmh/tempo; empty-state pattern shared with efficiency chart. |
| `renderPaceHrChart(sessions)` | Pace vs HR scatter — X=`gjsnittspuls`, Y=`tempo` (seconds/km) or km/h depending on global `paceUnit`; Y-axis inverted in pace mode, normal in kmh mode; same per-type color coding, regression line, legend, and toggle pattern as `renderSleepHrChart` (`paceHrTypeFilter`); tooltip adapts label to unit. |
| `renderVenueChart(sessions)` | Stacked bar chart (last 20 weeks): outdoor km (green) vs treadmill km (blue). Hidden when no treadmill sessions. |
| `renderHeatmap(sessions)` | Training calendar heatmap — GitHub-style grid, 4 modes: distance (blue intensity), belastning (zone-load intensity), økttype (coloured by dominant type), pulssone (coloured by dominant HR zone). `dailyData` entries carry `zones:[0,0,0,0,0]` and `ids:[]` for zone mode and click navigation. Click handler registered once in `DOMContentLoaded` via delegation on `#heatmapContainer` → single session: `DetailPanel.openSession`; multiple sessions same day: `DetailPanel.openWeek`. Custom tooltip registered the same way. Stats bar (`#heatmapStats`) shows active days, total km, current/longest streak for the visible period. Uses DashFilter year for range. Reads `input[name="heatmetric"]` radio for mode. |
| `eventLinesPlugin` | Chart.js globally registered plugin (`Chart.register(eventLinesPlugin)`). Runs on ALL charts. Draws dashed vertical lines (point events) or semi-transparent shaded bands with dashed borders (range events with `endDate`). Safely no-ops on charts where labels don't match. Guarded with double try-catch so errors never crash chart rendering. |
| `computeRecords(sessions)` | Returns general records + `distPRs` array (5k/10k/halvmaraton/maraton — fastest session per distance bracket). Also tracks `bestRacePace` (fastest Race session by tempo). Streak uses Monday-aligned epoch week index for correct ISO week / year-boundary handling. |
| `computePerfCurve(sessions)` | Returns array of 7 performance curve entries (400m, 1k, 5k, 10k, 15k, half, marathon). For each distance: (1) manual override from `Store.data.bestEfforts`; (2) actual Test/Race session in ±10% range; (3) Riegel estimate `t2 = t1 × (km/anchor.distanse)^1.06` from closest Test/Race anchor ≥1 km; (4) dash. 400m never gets Riegel estimate. Returns `{ label, value, sub, estimated }` per entry. |
| `renderZoneChart(sessions)` | Standalone function; reads `zoneGroupBy` ('week'/'month') to group data |
| `fmtWeekLabel(wk)` | Formats a `YYYY-WW` string as `"Uke N 'YY"` — used for all weekly chart display labels; defined near `isoWeek` |
| `absWeekNum(d)` | Monday-aligned epoch week integer — `Math.floor((Date+3days)/7days)`; used for consecutive-week streak and consistency calculations across `renderConsistency`, `computeBlocks`, `DetailPanel.openBlock`, `computeRecords` |
| `getZoneForHr(hr, zones)` | Returns 0-indexed zone number for a given BPM value against a `zones` array (`settings.zones`); returns -1 if HR is outside all configured zones or zones is empty |
| `calcZoneDistribution(sessions)` | Aggregates `soner` arrays across a session array; returns `{ totals:[s,s,s,s,s], total, pcts:[%,%,%,%,%] }` — used in training block drill-down for the Sonefordeling section |
| `avgPaceHR(sessions)` | Returns `{ avgPace, avgHR }` (rounded seconds/km and bpm, or null) — shared helper used in `computeBlocks`, `openWeek`, `openShoe` |
| `toSafeAttr(obj)` | JSON-serializes an object and escapes `&` and `"` for safe embedding in HTML attributes — used by `renderBlocks` for `data-block` |
| `formatSessionTsv(sessions)` | Returns a TSV string (header + one row per session) in Excel-compatible format: Dato `M/D/YYYY`, Uke `YYYY-WW`, Varighet/zones as `H:MM:SS`, Tempo as `MM:SS`, Søvn as `H:MM`, decimals as dot. 20 columns matching the original Excel log. |
| `tsvIsoWeek(dateStr)` | Computes ISO week as `YYYY-WW` string (e.g. `2026-20`) from a `YYYY-MM-DD` date. Used by `formatSessionTsv` — separate from `isoWeek()` which returns a display label. |
| `copyToClipboard(text)` | Async: tries `navigator.clipboard.writeText`; falls back to `execCommand('copy')` via a hidden textarea. Returns `true` on success. |
| `showChartEmpty(canvasId, show, msg)` | Unified empty-state helper for all charts. Removes any existing `.chart-no-data` element from the canvas's `.chart-wrap` parent, then either hides the canvas and appends a centred message div (when `show` is truthy) or shows the canvas (when falsy). Default message: `'Ingen data å vise'`. All 8 chart render functions call this instead of duplicating inline DOM logic. |
| `malCell(s)` | Returns colour-coded HTML for the log table "Mål km" cell; blue ≥105%, green ≥100%, amber ≥80%, red <80% of target; empty string if `malDistanse` is null |
| `minsToHm(m)` | Formats decimal minutes as `h:mm` (e.g. `90.5` → `"1:30"`); used in Pulssoner chart ticks and tooltips |
| `refreshAll()` | Called after any data change; re-renders log, shoe list, dashboard if visible |
| `switchTab(name)` | Tab navigation; triggers tab-specific render; also toggles `body.is-dash` class — used by CSS to suppress sticky header/tabs on the dashboard (only filter bar sticks there) |

Global state:
- `let zoneGroupBy = 'week'` — controls Uke/Måned toggle for zones chart; reset by Nullstill
- `let aeVenueFilter = 'all'` — controls Alle/Utendørs/Tredemølle toggle for aerobic efficiency chart
- `let aeZ2Filter = 'all'` — controls Alle Easy / Sone 2 toggle for aerobic efficiency chart; reset by Nullstill
- `let sleepHrTypeFilter = 'Easy'` — session-type filter for Søvn vs puls scatter ('alle'/'Easy'/'Langtur')
- `let paceHrTypeFilter = 'Easy'` — session-type filter for Tempo vs puls scatter ('alle'/'Easy'/'Langtur')
- `let z2PaceTypeFilter = 'alle'` — session-type filter for Tempo i sone 2 ('alle'/'Easy'/'Langtur')
- `let paceUnit = 'pace'` — global unit toggle for all pace charts ('pace'=min/km / 'kmh'=km/t); radio buttons in dashboard filter bar; re-renders Tempo per uke, Z2Pace, and PaceHr charts on change; reset by Nullstill
- `let cachedBlocks = []` — result of last `computeBlocks` call; set in `renderDashboard` before `renderBlocks`; read by `renderBlocks` and `DetailPanel.openBlock` to avoid recomputing on every filter change and panel open

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
- **Drive guard:** The entire `supportsApi` block (handle recovery + `requestPermission` + picker) is wrapped in `!DriveIO.isSignedIn()`. When Drive is connected, saves go exclusively to Drive — no local file dialogs ever appear, even if a handle is stored in IndexedDB.

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
- Matching order: (1) `evt.date` exact string, (2) `isoWeek(evt.date)` (returns `YYYY-WW`), (3) nearest label ≥ `evt.date` via `findIndex` — **only when the event date falls within the chart's visible label range** (guarded by `evt.date >= rawLabels[0] && evt.date <= rawLabels[rawLabels.length-1]`). The bounds guard prevents out-of-range events snapping to the first data point on date-labeled charts like efficiency and Z2 pace.
- PMC chart uses daily ISO date labels → matches `evt.date` directly.
- Load, weekly dist, and pace charts use formatted display labels (`"Uke 21 '26"`) but all store `_rawLabels` (raw `YYYY-WW`) on `chart.data` → plugin reads `chart.data._rawLabels` first.
- Range events (`endDate` present): draws a `rgba(..., 0.12)` filled rect + dashed start line. End line drawn only when the end label is found. **End-date finding order**: (1) exact match, (2) `isoWeek` match, (3) nearest session-week before the end date (handles gaps where the end week had no sessions). If end is beyond the visible range entirely, band extends to the right edge with no end line.
- Band edges: both dashed lines and the filled rect use the same `xStart = x - colWidth/2` and `xEnd = meta.data[idx2].x + colWidth/2` coordinates — no offset between line and band boundary.

### Mobile layout (`@media (max-width: 600px)`)
- `html { overflow-x: hidden }` — prevents horizontal page scrolling
- `.dash-grid > * { min-width: 0 }` — allows dashboard cards to shrink below content width so Chart.js sizes charts correctly; `overflow: hidden` intentionally omitted — it would clip Chart.js built-in tooltips (position:absolute) at the card boundary
- `.cs-stat { flex: 1 1 75px }` — consistency stats row shrinks to fit instead of overflowing at 110px minimum
- `.form-grid-4 { grid-template-columns: repeat(2,1fr) }` — Ytelse and trailing-row form sections drop from 4 to 2 columns
- `.zone-grid { grid-template-columns: repeat(3,1fr) }` — zone inputs drop from 5 to 3 columns
- Log table: 9 secondary columns hidden via `nth-child` (see Treningslogg section above)
- Tabs: `overflow-x: auto; flex-wrap: nowrap` — tabs scroll horizontally rather than wrapping
- `#heatmapContainer { overflow-x: auto }` is applied globally (not just mobile) — heatmap always scrolls within its card
- `768px` breakpoint (existing): `.dash-grid` already drops to 1 column

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

### Completed
- **Google Drive sync** — OAuth 2.0 PKCE flow, `drive.file` scope, refresh token in localStorage, silent sync on every save

### Phase 3 — Hosting
- **GitHub Pages** for the HTML file (free static hosting) — not yet enabled
- Redirect URI for Drive OAuth will need updating to the Pages URL once live
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
