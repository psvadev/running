# Løpelogger — Project Handoff

## What this is
A self-contained single-file running tracker web app (`løpelogger.html`) that replaces the user's multi-tab Excel workbook. Norwegian UI throughout.

## File locations
- **App:** `c:\temp\GitHub\running\løpelogger.html`
- **Data:** wherever the user saves their `løpelogger.json` (opened via File System Access API in Edge/Chrome)

---

## Tech stack
| Concern | Choice |
|---|---|
| Structure | Single `.html` file, no build step, no framework |
| Charts | Chart.js 4.4.0 (CDN) |
| Excel import | SheetJS xlsx 0.18.5 (CDN) |
| Data storage | Local JSON file via File System Access API (Edge/Chrome auto-save); download/upload fallback for Firefox |
| Language | Vanilla JS, no TypeScript |

---

## Data model (`løpelogger.json`)
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
    "stigning": 1.0,               // %
    "sko": "ASICS Novablast 5",
    "sovn": 6.87                   // decimal hours (e.g. 6.87 = 6h52m); display via hoursToHHMM()
  }],
  "shoes": ["ASICS Novablast 5", "Saucony Ride 18", "Adidas trainers"],
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

## App structure (4 tabs)

### Small field tweaks
- **Stigning**: `step="0.5"` — spinner moves in 0.5% increments

### ➕ Legg til økt (form tab)
- Fields in **Excel column order**: Dato, Uke (auto), Øktnavn, Økt-type, Treningsplan, Varighet (auto), Distanse, Gj.snittspuls, Toppuls, Sone 1–5, Kalorier, Tempo (auto), Snitt km/t (auto), Stigning, Sko, Søvn
- Layout: 4 sections
  - **Øktinfo** (5-col auto-fill): Dato, Uke, Øktnavn, Økt-type, Treningsplan
  - **Ytelse** (4-col fixed): Varighet, Distanse, Gj.snittspuls, Toppuls
  - **Pulssoner** (5-col zone-grid): Sone 1–5
  - **Trailing row** (3-col, 2 rows): Kalorier, Tempo, Snitt km/t → Stigning, Sko, Søvn
- Auto-calculated (readonly, shown in accent blue): Varighet (sum of zones), Tempo, Snitt km/t
- Shoe dropdown has a `+` button that navigates to Innstillinger tab
- Edit mode: clicking a row in the log pre-fills the form; edit banner shown; "Oppdater økt" replaces "Lagre økt"

### 📊 Oversikt (dashboard tab — full width)
- Filter bar at top: økt-type dropdown, treningsplan dropdown, year pills (toggle individual years), Nullstill button
- **Yearly goal card** (full-width, hidden if no goal set): progress bar, km løpt, km igjen, Prognose (year-end projection), km/uke nødvendig. Green if on track, warning if projected to fall short.
- Charts (all **week-based**, not per-session — except Records):
  - **Rekorder** — best pace, longest dist, longest time, best km/h, total dist, total time, best week (km), longest streak (consecutive weeks) — per-session level, full-width
  - **Ukentlig distanse** — bar chart, km per week (last 20 weeks)
  - **Tempo per uke** — line chart, weighted average pace per week (total time ÷ total km)
  - **Pulssoner** — stacked bar, minutes per zone per week, last 20 weeks; **Uke/Måned toggle** switches grouping
  - **Årssammenligning** — cumulative km by week number, one line per year (full-width); **hidden when exactly one year is selected** in the filter (card id: `yearCompCard`)
  - Shoe km horizontal bars
  - Weekly summary table (scrollable)

### 📋 Treningslogg (log tab — full width)
- Full-width sortable table (click column headers)
- Filters: fra/til dato, økt-type, sko
- Row actions: ✏️ edit (goes to form tab), 🗑️ delete (with confirm)
- **"Importer Excel/CSV"** button → SheetJS modal with preview before confirming

### ⚙️ Innstillinger (settings tab — max 1200px)
- **Mål**: add yearly km goals (year + km); listed with delete button; triggers goal card on dashboard
- **Profil & Puls**: max HR, resting HR, 5 zone BPM boundaries, "Auto-beregn" button (fills zones at 50/60/70/80/90% of max HR)
- **Sko**: add by name (Enter or button), shows km per shoe, remove button
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
| `FileIO` | File System Access API wrapper; `open()`, `save()`, `download()`, `loadCache()` |
| `Form` | Form read/write; `read()`, `populate()`, `save()`, `editSession()`, `autoCalcVarighet()`, `autoCalcPace()` |
| `Log` | Session table render + sort/filter |
| `DashFilter` | Dashboard filter state (years Set, type, plan); `get(sessions)` returns filtered array |
| `Settings` | Shoe management, goal management, zone editor, profile save, file controls |
| `Import` | SheetJS parse, Norwegian column mapping, preview modal, `mergeSessions` dedup |
| `renderDashboard()` | Rebuilds all chart panels and goal card; calls `buildYearPills()`; hides `yearCompCard` when single year selected |
| `computeRecords(sessions)` | Returns `{ bestePace, longestDist, longestTime, bestKmh, totalDist, totalTime, besteUke, besteUkeKm, longestStreak }`. Streak uses absolute week index (`Math.floor(date / 7days)`) so year-boundary weeks are handled correctly. |
| `renderZoneChart(sessions)` | Standalone function; reads `zoneGroupBy` ('week'/'month') to group data |
| `refreshAll()` | Called after any data change; re-renders log, shoe list, dashboard if visible |
| `switchTab(name)` | Tab navigation; triggers tab-specific render |

Global state:
- `let zoneGroupBy = 'week'` — controls Uke/Måned toggle for zones chart

---

## Important quirks & fixes made during build

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

### Auto-calculated fields
- `varighet`, `tempo`, `snittkmh` are `readonly` inputs styled with accent colour and no border.
- They are set programmatically; the form's `clear()` still resets them.

### New file save flow
- When no file handle exists, `FileIO.save()` calls `showSaveFilePicker()` → browser shows Save As dialog on first save.
- Subsequent saves are automatic (handle is retained in memory for the session).
- `AbortError` (user cancels dialog) is handled gracefully.
- Only works in Edge/Chrome; Firefox users must use the "Last ned" button in Innstillinger.

### Goals data
- Stored as `Store.data.goals: { "YYYY": km }` — plain object keyed by year string.
- `_migrate()` ensures `goals` exists on old files that pre-date this feature.
- Dashboard goal card is hidden if no goal is set for the target year.
- Target year = single selected year in filter, otherwise current calendar year.

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
- Year comparison chart uses `allSessions` (ignores type/plan filter) — known inconsistency; hidden automatically when only one year is selected (nothing to compare)

---

## How to open and test
1. Open `løpelogger.html` in **Edge** or **Chrome**
2. Go to ⚙️ Innstillinger → click **📂 Åpne fil** → select your `løpelogger.json`
3. Data loads; all tabs refresh automatically
4. In **Firefox**: same, but use "⬇️ Last ned" to save changes (no auto-save)

## Saving a new file (Edge/Chrome)
- Click **✨ Ny fil** → enter some data → click **💾 Lagre** in the header (or save a session)
- Browser shows a "Save As" dialog on the first save; pick folder and filename (default: `løpelogger.json`)
- All future saves are automatic

## Re-importing Excel data
- Export the Excel sheet as `.xlsx` or `.csv`
- Go to 📋 Treningslogg → **Importer Excel/CSV**
- Preview shown before confirming; duplicates are skipped automatically
- If re-importing to fix data (e.g. søvn), clear sessions first via Innstillinger → Tøm alle data, then re-import
