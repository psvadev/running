# Løpelogger

A self-contained single-file running tracker that replaces a multi-tab Excel workbook. Norwegian UI throughout.

## Features

### Logging
- Log runs with date, session type, training plan, duration, distance, HR (avg + max), 5 HR zones, calories, pace, avg km/h, incline, shoe, and sleep
- Auto-calculated fields: duration (summed from zones), pace, avg km/h
- Edit any past session by clicking it in the log

### Dashboard (Oversikt)
- **Yearly goal card** — progress bar with km done, km remaining, year-end projection, and required weekly km to stay on track
- **Rekorder** — best pace, longest session (time + distance), best avg km/h, total distance and time, best week, longest streak; plus distance PRs for 5 km, 10 km, half marathon, and marathon
- **Treningsbelastning per uke** — weekly training load scored by zone intensity (Z1=1 … Z5=5 points/min), color-coded bars with 4-week rolling average
- **Treningsstatus (PMC)** — Performance Management Chart: Fitness (CTL, 42-day), Fatigue (ATL, 7-day), and Form (TSB = CTL−ATL) over the last 365 days
- **Ukentlig distanse** — km per week, last 20 weeks
- **Tempo per uke** — weighted average pace per week
- **Aerob effektivitet** — aerobic efficiency trend for Easy sessions (speed ÷ heart rate), with rolling average and personal average reference line
- **Pulssoner** — stacked minutes per zone per week or month (toggle)
- **Årssammenligning** — cumulative km by week number, one line per year
- **Sko-kilometer** — total km per shoe pair
- **Ukentlig oversikt** — scrollable summary table (sessions, distance, time, avg pace per week)

Dashboard filters: session type, training plan, year pills — all charts update live.

### Session log (Treningslogg)
- Full sortable table — click any column header to sort
- Filter by date range, session type, and shoe
- Edit or delete any row

### Import
- Import from `.xlsx` or `.csv` via SheetJS — preview before confirming
- Duplicates skipped automatically (matched on date + distance + duration)
- Maps all Norwegian column headers from the original Excel workbook

### Settings (Innstillinger)
- **Yearly goals** — set a km target per year; tracked on the dashboard
- **Profil & Puls** — max HR, resting HR, 5 zone boundaries; auto-calculate zones from max HR
- **Sko** — manage shoe list with km totals; used in the log filter and form dropdown
- **Datafil** — open, create, download, or clear all data

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
