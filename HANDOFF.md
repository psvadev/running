# Løpelogger — Project Handoff

## What this is
A self-contained single-file running tracker web app (`løpelogger.html`) that replaces the user's multi-tab Excel workbook. Norwegian UI throughout.

## File locations
- **App:** `c:\temp\GitHub\running\løpelogger.html`
- **Repo:** `https://github.com/psvadev/running` (private)
- **Data:** wherever the user saves their `løpelogger.json` (opened via File System Access API in Edge/Chrome)

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

## Data model (`løpelogger.json`)

> **Note on shoes:** Stored as objects (`{ name, retirementKm?, startDate? }`) since migration added in v2. Old files with string arrays are migrated automatically by `Store._migrate()`.


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
    "sko": "ASICS Novablast 5",
    "sovn": 6.87                   // decimal hours (e.g. 6.87 = 6h52m); display via hoursToHHMM()
  }],
  "shoes": [
    { "name": "ASICS Novablast 5", "retirementKm": 650 },
    { "name": "Saucony Ride 18" }
  ],
  "events": [
    { "id": "abc123", "date": "2026-01-15", "title": "Start Runna 10K", "type": "plan" },
    { "id": "def456", "date": "2026-02-01", "endDate": "2026-02-10", "title": "Forkjølet", "type": "illness" }
  ],
  "goals": {
    "2026": 705                    // yearly km goal; keyed by year string
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
  - **Øktinfo** (5-col auto-fill): Dato, Uke, Øktnavn, Økt-type, Treningsplan
  - **Ytelse** (4-col fixed): Varighet, Distanse, Gj.snittspuls, Toppuls
  - **Pulssoner** (5-col zone-grid): Sone 1–5
  - **Trailing row** (3-col, 2 rows): Kalorier, Tempo, Snitt km/t → Stigning, Sko, Søvn
- Auto-calculated (readonly, shown in accent blue): Varighet (sum of zones), Tempo, Snitt km/t
- Stigning: `step="0.5"` — spinner moves in 0.5% increments
- Shoe dropdown has a `+` button that navigates to Innstillinger tab
- Edit mode: clicking a row in the log pre-fills the form; edit banner shown; "Oppdater økt" replaces "Lagre økt"

### 📊 Oversikt (dashboard tab — full width)
- Filter bar at top: økt-type dropdown, treningsplan dropdown, year pills (toggle individual years), Nullstill button
- **Yearly goal card** (full-width, hidden if no goal set): progress bar, km løpt, km igjen, Prognose (year-end projection), km/uke nødvendig. Green if on track, warning if projected to fall short.
- Charts (all **week-based**, not per-session — except Records):
  - **Rekorder** — general records (best pace, longest dist/time, best km/h, total dist/time, best week, longest streak) + **Distanse-PR** sub-section (5 km, 10 km, Halvmaraton, Maraton — fastest session per bracket)
  - **Treningsbelastning per uke** — bar chart, weekly load score (zone minutes × zone weight Z1=1…Z5=5); bars color-coded green/amber/red relative to personal max; blue 4-week rolling average line overlay (full-width)
  - **Treningsstatus (PMC)** — line chart, last 365 days; three lines: Kondisjon/CTL (42-day exp. avg, blue), Tretthet/ATL (7-day exp. avg, red), Form/TSB (CTL−ATL, green). Always uses `allSessions` regardless of dashboard filter — CTL/ATL require full history to be meaningful (full-width)
  - **Ukentlig distanse** — bar chart, km per week (last 20 weeks). Supports event marker lines.
  - **Tempo per uke** — line chart, weighted average pace per week (total time ÷ total km)
  - **Aerob effektivitet (Easy-økter)** — line chart; per-session score = `snittkmh / gjsnittspuls × 100` for Easy sessions only; individual points + 4-session rolling average (green) + personal average reference line (dashed amber). Tooltip shows session name, speed, and HR. Responds to dashboard filter
  - **Pulssoner** — stacked bar, minutes per zone per week, last 20 weeks; **Uke/Måned toggle** switches grouping
  - **Årssammenligning** — cumulative km by week number, one line per year (full-width); **hidden when exactly one year is selected** (card id: `yearCompCard`); responds to type/plan filters
  - **Treningskalender** — GitHub-style heatmap calendar (full-width). Three modes toggled via radio: *Distanse* (blue intensity by quartile), *Belastning* (zone-weighted load by quartile), *Økttype* (cell coloured by dominant session type). Hover shows date + session details. Shows last 52 weeks; if single year selected, shows full calendar year. Type mode includes a colour legend. **Cell size is dynamic** — calculated from `container.offsetWidth` to fill the card width (min 10px).
  - Shoe km horizontal bars. Shows ⚠️/🔴 warning when approaching/exceeding retirement km.
  - Weekly summary table (scrollable)

### 📋 Treningslogg (log tab — full width)
- Full-width sortable table (click column headers); columns include **Plan** (treningsplan) after Navn
- Filters: fra/til dato, økt-type, **treningsplan (Plan)**, sko — all wired to `fFilterPlan` etc.; Nullstill clears all
- Row actions: ✏️ edit (goes to form tab), 🗑️ delete (with confirm)
- **"Importer Excel/CSV"** button → SheetJS modal with preview before confirming

### 📅 Planlegging (planning tab — max 1200px)
- **Mål**: add yearly km goals (year + km); listed with delete button; triggers goal card on dashboard
- **Sko**: add by name + optional retirement km. Shows progress bar + projected retirement date (8/12-week rate). Old string-only JSON files migrated automatically.
- **Hendelser**: add timeline events (start date, optional end date, type, title). Types: **plan / race / illness / vacation / personal**. Point events = dashed vertical line; range events (with `endDate`) = semi-transparent shaded band with dashed borders. Toggled via "Hendelser" checkbox in dashboard filter bar. Event list shows date range as "DD. MMM – DD. MMM" when endDate present.

### ⚙️ Innstillinger (settings tab — max 1200px)
- **Profil & Puls**: max HR, resting HR, 5 zone BPM boundaries, "Auto-beregn" button (fills zones at 50/60/70/80/90% of max HR)
- **Datafil**: open file, new file, download/export, "Tøm alle data" danger button

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
| `Form` | Form read/write; `read()`, `populate()`, `save()`, `editSession()`, `autoCalcVarighet()`, `autoCalcPace()` |
| `Log` | Session table render + sort/filter |
| `DashFilter` | Dashboard filter state (years Set, type, plan); `get(sessions)` returns filtered array |
| `Settings` | Shoe management, goal management, zone editor, profile save, file controls |
| `Import` | SheetJS parse, Norwegian column mapping, preview modal, `mergeSessions` dedup |
| `renderDashboard()` | Rebuilds all chart panels and goal card; calls `buildYearPills()`; hides `yearCompCard` when single year selected |
| `renderPMCChart(allSessions)` | PMC chart — walks every calendar day from first session to today, accumulating CTL and ATL via exponential decay; displays last 365 days. Always called with `allSessions` (not filtered). |
| `renderEfficiencyChart(sessions)` | Aerobic efficiency chart — filters to Easy sessions with HR+speed data, computes score = `snittkmh/gjsnittspuls×100`, renders points + 4-session rolling avg + personal average reference line |
| `renderHeatmap(sessions)` | Training calendar heatmap — GitHub-style grid, 3 modes: distance (blue intensity), belastning (zone-load intensity), økttype (coloured by dominant type). Uses DashFilter year for range. Reads `input[name="heatmetric"]` radio for mode. |
| `eventLinesPlugin` | Chart.js globally registered plugin (`Chart.register(eventLinesPlugin)`). Runs on ALL charts. Draws dashed vertical lines (point events) or semi-transparent shaded bands with dashed borders (range events with `endDate`). Safely no-ops on charts where labels don't match. Guarded with double try-catch so errors never crash chart rendering. |
| `computeRecords(sessions)` | Returns general records + `distPRs` array (5k/10k/halvmaraton/maraton — fastest session per distance bracket). Streak uses Monday-aligned epoch week index for correct ISO week / year-boundary handling. |
| `renderZoneChart(sessions)` | Standalone function; reads `zoneGroupBy` ('week'/'month') to group data |
| `refreshAll()` | Called after any data change; re-renders log, shoe list, dashboard if visible |
| `switchTab(name)` | Tab navigation; triggers tab-specific render (`dash`→`renderDashboard`, `log`→`Log.render`, `plan`/`settings`→`Settings.render`) |

Global state:
- `let zoneGroupBy = 'week'` — controls Uke/Måned toggle for zones chart

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
- Weekly dist chart uses raw `YYYY-WW` labels → matches via `isoWeek`.
- Load chart uses formatted display labels (`"Uke 21 '26"`) but stores `_rawLabels: loadWeeks` (raw `YYYY-WW`) on `chart.data` → plugin reads `chart.data._rawLabels` first, so week matching still works.
- Range events (`endDate` present): draws a `rgba(..., 0.12)` filled rect between the two week columns + dashed lines at each edge. Single events: just a dashed line.

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
- Replace local JSON with a single `løpelogger.json` in Google Drive
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
- Fitness & Fatigue (PMC) chart — rolling 42-day vs 7-day training load averages; discussed but not yet implemented

---

## How to open and test
1. Open `løpelogger.html` in **Edge** or **Chrome**
2. Go to **⚙️ Innstillinger** → click **📂 Åpne fil** → select your `løpelogger.json`
3. Data loads; all tabs refresh automatically
4. On subsequent loads the app will attempt to reattach the file handle automatically
5. In **Firefox**: same, but use "⬇️ Last ned" to save changes (no auto-save)

## Saving a new file (Edge/Chrome)
- Click **✨ Ny fil** → enter some data → click **💾 Lagre** in the header (or save a session)
- Browser shows a "Save As" dialog on the first save; pick folder and filename (default: `løpelogger.json`)
- All future saves are automatic; handle persists across page reloads via IndexedDB

## Re-importing Excel data
- Export the Excel sheet as `.xlsx` or `.csv`
- Go to 📋 Treningslogg → **Importer Excel/CSV**
- Preview shown before confirming; duplicates are skipped automatically
- If re-importing to fix data (e.g. søvn), clear sessions first via Innstillinger → Tøm alle data, then re-import
