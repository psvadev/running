# Løpelogger

A self-contained single-file running tracker that replaces a multi-tab Excel workbook.

## Features

- Log runs with pace, distance, heart rate, HR zones, sleep, and more
- Dashboard with weekly charts, yearly goal tracking, and records
- Full session history with sorting, filtering, and Excel/CSV import

## Usage

Open `løpelogger.html` in Edge or Chrome. On first use, go to **⚙️ Innstillinger** to set up your data file. Data is saved automatically to a local `løpelogger.json` file you keep wherever you like.

Firefox is supported but requires manually downloading the JSON after each session to save changes.

## Stack

Single `.html` file — no build step, no framework, no install.

- [Chart.js](https://www.chartjs.org/) — charts
- [SheetJS](https://sheetjs.com/) — Excel/CSV import
- File System Access API — local file read/write
