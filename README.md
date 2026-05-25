# Løpelogger

A self-contained single-file running tracker that replaces a multi-tab Excel workbook.

## Features

- Log runs with pace, distance, heart rate, HR zones, sleep, and more
- Dashboard with weekly charts, yearly goal tracking, and records
- Full session history with sorting, filtering, and Excel/CSV import
- Auto-saves to a local JSON file (Edge/Chrome); download fallback for Firefox

## Usage

1. Open `løpelogger.html` in Edge or Chrome
2. Go to **⚙️ Innstillinger** → **📂 Åpne fil** to load or create a data file
3. Add sessions in **➕ Legg til økt**, view stats in **📊 Oversikt**

Data is stored in a separate `løpelogger.json` file you keep wherever you like.

## Stack

Single `.html` file — no build step, no framework, no install.

- [Chart.js](https://www.chartjs.org/) — charts
- [SheetJS](https://sheetjs.com/) — Excel/CSV import
- File System Access API — local file read/write
