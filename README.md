# Løpelogger

A self-contained single-file running tracker that replaces a multi-tab Excel workbook.

## Features

- Log runs with pace, distance, heart rate, HR zones, sleep, and more
- Dashboard with weekly charts, yearly goal tracking, and records
- Full session history with sorting, filtering, and Excel/CSV import
- Auto-saves to a local JSON file (Edge/Chrome); manual download fallback for Firefox

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
3. The app remembers the file; next time you open it a one-click prompt restores access without re-picking the file

### Importing from Excel or CSV

1. Go to **📋 Treningslogg** → click **Importer Excel/CSV**
2. Select your `.xlsx` or `.csv` file — a preview is shown before anything is saved
3. Duplicates are skipped automatically (matched on date + distance + duration)

## Firefox

Firefox does not support the File System Access API, so auto-save is unavailable.

- Load data: **⚙️ Innstillinger** → **📂 Åpne fil** (standard file input)
- Save data: **⚙️ Innstillinger** → **⬇️ Last ned** after each session to download the updated JSON
- Re-open the downloaded file next time to continue where you left off

## Stack

Single `.html` file — no build step, no framework, no install.

- [Chart.js](https://www.chartjs.org/) — charts
- [SheetJS](https://sheetjs.com/) — Excel/CSV import
- File System Access API — local file read/write (Edge/Chrome)
