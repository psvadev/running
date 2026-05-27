# Løpelogger

A self-contained single-file running tracker that replaces a multi-tab Excel workbook. Norwegian UI throughout.

## Features

### Logging
- Log runs with date, session type, training plan, duration, distance, HR (avg + max), 5 HR zones, calories, pace, avg km/h, incline, shoe, sleep, and **run type** (outdoor / treadmill)
- Auto-calculated fields: duration (summed from zones), pace, avg km/h
- Edit any past session by clicking it in the log

### Dashboard (Oversikt)
- **Yearly goal card** — progress bar with km done, km remaining, year-end projection, and required weekly km to stay on track
- **Rekorder** — best pace, longest session (time + distance), best avg km/h, total distance and time, best week, longest streak; plus distance PRs for 5 km, 10 km, half marathon, and marathon
- **Innsikter** — auto-generated insight tiles: km milestones, most-used shoe, heaviest 4-week training block, fastest Easy run, most active month
- **Treningsrytme** — consistency score 0–100 over the last 12 weeks (active-week rate, volume threshold weeks, streak bonus); configurable km/run-count thresholds in Settings; monthly active-weeks trend chart
- **Treningsblokker** — auto-generated training block cards from Plan events; active block is a full-width hero card with consistency progress bar and weekly km sparkline; past blocks shown as compact cards below; click any card for full analytics (pace, HR, indoor/outdoor split, shoes, optional target tracking)
- **Treningsbelastning per uke** — weekly training load scored by zone intensity (Z1=1 … Z5=5 points/min), color-coded bars with 4-week rolling average
- **Treningsstatus (PMC)** — Performance Management Chart: Fitness (CTL, 42-day), Fatigue (ATL, 7-day), and Form (TSB = CTL−ATL) over the last 365 days
- **Ukentlig distanse** — km per week, last 20 weeks
- **Tempo per uke** — weighted average pace per week
- **Aerob effektivitet** — aerobic efficiency trend for Easy outdoor sessions (speed ÷ heart rate), with rolling average and personal average reference line; treadmill sessions excluded automatically
- **Interactive charts** — hover any weekly chart for a full week summary (km, løp, tid, tempo, HR); click a bar/point to open a drill-down detail panel for that week; click a shoe bar to open shoe detail; click a heatmap day to open session or week detail
- **Ute vs inne** — weekly stacked bar splitting km between outdoor (🏃) and treadmill (⚙️); hidden until first treadmill session is logged
- **Pulssoner** — stacked minutes per zone per week or month (toggle)
- **Årssammenligning** — cumulative km by week number, one line per year
- **Sko oversikt** — total km per shoe pair + per-shoe stats: run count, avg pace, avg HR, last used date
- **Ukentlig oversikt** — scrollable summary table (sessions, distance, time, avg pace per week)

Dashboard filters: session type, training plan, run type (outdoor/treadmill), year pills — all charts update live.

### Session log (Treningslogg)
- Full sortable table — click any column header to sort
- Filter by date range, session type, run type (outdoor/treadmill), and shoe
- Edit or delete any row

### Import
- Import from `.xlsx` or `.csv` via SheetJS — available under **⚙️ Innstillinger → Datafil**
- Preview before confirming; duplicates skipped automatically (matched on date + distance + duration)
- Maps all Norwegian column headers from the original Excel workbook

### Settings (Innstillinger)
- **Yearly goals** — set a km target per year; tracked on the dashboard
- **Profil & Puls** — max HR, resting HR, 5 zone boundaries; auto-calculate zones from max HR
- **Treningsrytme** — km-grense and løp-grense per week used to compute the consistency score
- **Sko** — manage shoe list with km totals; **Pensjonér** a shoe to hide it from the form dropdown while keeping historical data; **Aktiver** restores it; used in the log filter and form dropdown
- **Datafil** — open, create, download, import Excel/CSV, or clear all data

---

## Getting started

Open `løpelogger.html` in your browser — no install needed.

### First time (no existing data)

1. Go to **⚙️ Innstillinger** → click **✨ Ny fil**
2. Add a session in **➕ Legg til økt**, then click **💾 Lagre** in the header
3. A save dialog appears — pick a folder and name (default: `løpelogger.json`)
4. All future saves happen automatically in the background

### Loading an existing JSON file

1. Go to **⚙️ Innstillinger** → click **📂 Åpne fil**
2. Select your `løpelogger.json` — data loads immediately across all tabs
3. The app remembers the file; next time you open it a one-click prompt restores access without re-picking

### Importing from Excel or CSV

1. Go to **📋 Treningslogg** → click **Importer Excel/CSV**
2. Select your `.xlsx` or `.csv` file — a preview is shown before anything is saved
3. Duplicates are skipped automatically (matched on date + distance + duration)

#### Expected column headers

The first row must contain column headers. Header matching is case-insensitive. Only `dato` and `distanse` are required — all other columns are optional.

| Field | Accepted column names |
|---|---|
| Date *(required)* | `dato`, `date` |
| Distance km *(required)* | `distanse`, `distanse (km)`, `distance`, `km` |
| Session name | `øktnavn`, `oktnavn`, `session name` |
| Session type | `økt-type`, `okttype`, `type` |
| Training plan | `treningsplan`, `trenignsplan`, `training plan`, `plan` |
| Duration | `varighet`, `duration` |
| Avg HR | `gj.snittspuls`, `gjsnittspuls`, `avg hr`, `avg heart rate` |
| Max HR | `toppuls`, `max hr`, `max heart rate` |
| Zone 1–5 time | `sone1`–`sone5`, `sone1 (min)`–`sone5 (min)`, `zone1`–`zone5` |
| Calories | `kalorier`, `calories` |
| Pace (min/km) | `tempo`, `tempo (min/km)`, `pace` |
| Avg km/h | `snittkmh`, `snitt km/t`, `avg km/h` |
| Incline % | `stigning`, `stigning (%)`, `elevation` |
| Shoe | `sko`, `shoes` |
| Sleep | `søvn`, `sovn`, `sleep` |
| Week | `uke` |

**Date formats accepted:** ISO (`2025-05-26`), US (`05/26/2025`), Excel serial number.  
**Time formats accepted:** `H:MM:SS`, `MM:SS`, Excel fractional day.

---

## Firefox

Firefox does not support the File System Access API, so auto-save is unavailable.

- Load data: **⚙️ Innstillinger** → **📂 Åpne fil** (standard file input)
- Save data: **⚙️ Innstillinger** → **⬇️ Last ned** after each session to download the updated JSON
- Re-open the downloaded file next time to continue where you left off

---

## Stack

Single `.html` file — no build step, no framework, no install.

- [Chart.js 4.4.0](https://www.chartjs.org/) — charts
- [SheetJS xlsx 0.18.5](https://sheetjs.com/) — Excel/CSV import
- File System Access API — local file read/write (Edge/Chrome)
- IndexedDB — persists the file handle across page reloads so the file re-attaches automatically
