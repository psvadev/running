# Puls

A self-contained single-file running tracker — log a run in seconds with Strava-import, sync across devices via Google Drive, and follow your progress through records, insights, and trend charts. No install, no build step, no backend. Norwegian UI throughout.

## Features

### Logging
- Log runs with date, session type (Easy / Steady / Long / Tempo / Intervaller / Test / **Race** — plus your own custom types via Innstillinger), training plan (also extendable), duration, distance, HR (avg + max), 5 HR zones, calories, pace, avg km/h, incline % (treadmill) or **elevation gain in metres** (outdoor), shoe, sleep, **RPE (1–10)**, **run type** (outdoor / treadmill), **workout description** (only shown when Treningsplan = Runna — paste Runna programs or interval structures; appears above notes in the form and as `[Øktbeskrivelse]` in AI exports), and **notes** (free-text post-run context for AI analysis)
- Auto-calculated fields: duration (summed from zones), pace, avg km/h — check **Uten pulsdata** in the Pulssoner header to hide zones and enter duration manually (e.g. when running without a watch)
- **Hold utenfor analyse** — flag an atypical session (travel, illness, faulty HR strap, GPS glitch) so trends, insights, quality charts, and quality records skip it while its kilometres still count in all volume metrics, streaks, and totals; flagged sessions are always visibly marked (dimmed row in the log, an "Avvik" row in the session detail, and an `[Avvik]` tag in AI exports) — excluding is transparent, never silent; write the reason in Notater
- **Hent fra Strava** *(optional, requires Strava connection)* — button in the form pulls distance, duration, HR, HR zones, pace, elevation, and calories from a recent Strava activity, plus the Runna workout description when Runna pushed one to the activity (fills Øktbeskrivelse, never overwriting manually typed text); auto-selects automatically if exactly one run matches the date being logged, otherwise shows a picker (with a "Vis alle økter" link to always see the full list); only fills in fields — you still review and save manually. The activity's id is remembered on the saved session
- **Oppdater fra Strava** *(optional)* — when you edit a session that was originally filled from Strava, an "Oppdater fra Strava" button appears in the edit banner; it re-pulls that exact activity by id and refreshes only the Strava-derived fields (distance, duration, HR, zones, pace, elevation, calories) — your notes, Avvik flag, sleep, RPE, and shoes are left alone — then waits for you to review and save. Only appears on sessions logged from Strava going forward (older runs have no stored id)
- **Land** *(optional)* — the country a run took place in; leave it blank for home runs (empty means Norway) and only fill it for runs abroad. Norwegian country-name autocomplete; the field is prefilled from Strava when a fetched activity carries a country. Feeds the **Løpeatlas** tab
- After saving a new session, the app jumps to the session log automatically
- Edit any past session by clicking it in the log

### Dashboard (Oversikt)
- **Yearly goal card** — progress bar with km done, km remaining, year-end projection, and required weekly km to stay on track; a **dashed projection marker** on the bar shows where the year-end forecast lands relative to the goal (green if on track, red if short), so the gap to target is visible at a glance
- **Rekorder** — four sub-sections: **main grid** (total distance, total time, avg km/week, longest session by distance and time, best week, best month, best 4-week block, most elevation gain, total elevation gain (with Everest multiple), outdoor km, indoor km, best aerobic efficiency, lowest avg HR on a run ≥ 5 km, longest streak, current streak); **Pace** (best overall pace, best avg km/h, best Easy/Long/Tempo/Test/Race pace); **Distanse-PR** (5 km, 10 km, half marathon, marathon — fastest session per bracket); **Ytelseskurve** (performance curve for 400 m, 1 km, 5 km, 10 km, 15 km, half marathon, marathon — actual Test/Race sessions where available, Riegel formula estimates otherwise, manual overrides from Innstillinger take highest priority; estimated tiles shown in muted colour); **Topp 3 · Strava** (ranked top-3 recorded efforts per distance with dates, collected by the Strava best-efforts scan — outdoor GPS runs only, since Strava doesn't compute best efforts for treadmill activities; treadmill PRs stay covered by Distanse-PR); **Formkurve** (every Test/Race run Riegel-normalized to a 5K-equivalent time and plotted as one fitness curve over time — each new test race extends the curve instead of living as an isolated PR; up = fitter; appears once 2+ tests exist); aerobic efficiency and current streak are color-coded (red/amber/green/blue); aerobic efficiency tile has a hover tooltip explaining the scale (Lav < 4.0 · Moderat 4.0–5.5 · God 5.5–7.0 · Høy > 7.0)
- **Innsikter** — dynamic pool of insight candidates ranked by priority and recency; top 6 shown: km milestones (passed and upcoming — upcoming priority scales with proximity: 4 when <50 km, 2 when <100 km, 1 otherwise), shoe retirement warnings (warns at 85% of the shoe's configured km limit, urgent at 95% — falls back to 400/450 km when no limit is set), fastest Easy run, Easy pace trend (last 8 vs prior 8 weeks), **Easy HR trend** (avg HR last 8 vs prior 8 weeks — rising or falling), **volume trend** (last 4 weeks vs prior 4 weeks), **long run gap** (weeks since last Langtur), **elevation this month** (total høydemeter), **RPE trend** (Easy RPE avg last 8 vs prior 8 weeks, trending easier/harder — threshold 0.5 points; shows a distinct fatigue-flag variant instead when pace and HR both hold steady but RPE still climbs — an early overreaching signal), **race countdown** (days until next race event — priority 5 when ≤14 days), **streak-at-risk nudge** (fires Friday–Sunday when a ≥3-week running streak has no run yet that week), **plan-target progress** (total km vs the active Plan event's total-km target with a %-done vs %-of-time comparison; falls back to km-this-week vs the km/uke target, ✓-variant when reached), **fresh distance-PR celebration** (priority-5 tile for 14 days after a new Distanse-PR bracket record), **ramp-rate warning** (ACWR-lite: last 7 days' zone-weighted load vs the prior 28-day weekly average — warns above ×1.3, urgent above ×1.5, silent when training load is sensible), days since last run, Easy run Zone 2 compliance
- **Treningsrytme** — consistency score 0–100 over the last 12 weeks (active-week rate, volume threshold weeks, streak bonus); score breakdown bars show contribution of each component (max 50/30/20 pts); configurable km/run-count thresholds in Settings; monthly active-weeks trend chart; **availability-adjusted**: runless weeks covered by a Sykdom/Ferie event don't count against the score ("10 av 10 tilgjengelige uker") and the streak bridges them — running during a Ferie week still counts
- **Treningsblokker** — auto-generated training block cards from Plan events; active block is a full-width hero card with consistency progress bar and weekly km sparkline; past blocks shown as compact cards below; click any card for a rich drill-down: weekly progression bars (each row clickable → week detail; badges for Toppuke / Lengste løp / Raskest), auto-generated highlights (best week, longest run, streak, pace trend), consistency breakdown, HR zone distribution (stacked bar with low/high intensity summary), comparison vs previous block, and full run list
- **Treningsbelastning per uke** — weekly training load scored by zone intensity (Z1=1 … Z5=5 points/min), color-coded bars with 4-week rolling average
- **Treningsstatus (PMC)** — Performance Management Chart: Fitness (CTL, 42-day), Fatigue (ATL, 7-day), and Form (TSB = CTL−ATL) over the last 365 days
- **Ukentlig distanse** — km per week or month (Uke/Måned toggle); weekly mode shows last 20 weeks, monthly mode shows last 12 months; click a bar to drill into that week
- **Tempo per uke** — weighted average pace per week
- **Aerob effektivitet (rolige økter)** — aerobic efficiency trend (speed ÷ heart rate) for conversational-pace runs, with rolling average and personal average reference line. A rising trend means **lower HR at the same speed, or higher speed at the same HR** — improving aerobic form. **Run-type toggle** (Begge / Easy / Long) covers both easy and long runs; Steady/Tempo/Intervaller and other harder sessions are excluded by design (not Zone 2 targets). **Venue toggle** (Alle / Utendørs / Tredemølle) slices by run type; **Sone 2** filter isolates only runs where avg HR (or ≥70% of zone time) falls within configured Zone 2 — a cleaner aerobic signal that drops runs that drifted too hard
- **Interactive charts** — hover any weekly chart for a full week summary (km, løp, tid, tempo, HR); click a bar/point to open a drill-down detail panel for that week; click a shoe bar to open shoe detail; click a heatmap day to open session or week detail
- **Ute vs inne** — stacked bar splitting km between outdoor (🏃) and treadmill (⚙️); Uke/Måned toggle (week = last 26 weeks, month = last 12 months); hidden until first treadmill session is logged
- **Pulssoner** — stacked minutes per zone per week or month (toggle)
- **Årssammenligning** — cumulative km by week number, one line per year; summary table below the chart shows total km, run count, and avg km per active week per year (color-coded to match chart lines)
- **Sko oversikt** — total km per shoe pair + per-shoe stats: run count, avg pace, avg HR, last used date
- **Ukentlig oversikt** — scrollable summary table (sessions, distance, time, avg pace per week)

Dashboard filters: session type, training plan, run type (outdoor/treadmill), **tempo unit (min/km ↔ km/t)**, year pills — all charts update live. The tempo unit toggle switches "Tempo per uke" between pace and speed. **Nullstill** resets all filters including chart-local type pills, the pace unit toggle, and the Pulssoner Uke/Måned toggle.

**Mobile:** all charts resize to fit the screen width — no horizontal page scrolling. The training calendar scrolls horizontally within its own card.

### 🗺️ Løpeatlas (own tab)
A motivational travel section (grew out of "Land løpt i") that lives in its own tab — always fully expanded, no scrolling past it on the dashboard. It's laid out as three sectioned cards: **Reisestatistikk** — a row of stat tiles (land · verdensdeler N/6 · utenlandsøkter · utenlands totalt · lengste utenlands · nyeste land) with a venue meta line under a hairline (Første utenlands · 🏃 Mest ute *land* · ⚙️ Mest inne *land* — the top outdoor and top treadmill country abroad); **Land & verdensdeler** — a flag-chip strip of every country you've run in (flag + Norwegian name + all-time run count, Norway first, click a chip for that country's sessions) plus a continent-collection row of pills (Europa ✓ green / Afrika 🔒 muted …); and **Reiseutmerkelser** — **30+ auto-derived travel achievements** grouped Milepæler / Land / Verdensdeler / Distanse / Omgivelser / Sesong with progress bars on locked ones — foreign-country tiers (Passport Stamp → World Traveler → Frequent Flyer → Globetrotter), per-continent regional explorers (European Tour, Asia/Americas/Africa Explorer) + Continental Explorer / Global Runner / Cross-Continental / Both Hemispheres, Nordic Runner/Complete (under Verdensdeler), single-run distance milestones abroad (5K/10K/Half/Marathon) plus a cumulative-km-abroad ladder (Globe Starter 10 → Wanderer 25 → Explorer 50 → Miler 100 → Voyager 250) and Foreign Racer, surroundings (Scenic Route, Hotel Treadmill, an outdoor-countries ladder Outdoor Explorer 3 → Trail Nomad 5 → Wilderness Wanderer 10, and a single-run elevation ladder Foreign Hills 50 → Foreign Climber 200 → Foreign Summit 500 m) and season/time (Winter Escape, Multi-Year Traveler, plus a permanent per-year "New Year, New Country (2026) 🇸🇪" stamp for each year you first set foot in a brand-new country — the current year showing as a locked objective until you do). Everything is derived from your runs + events — nothing to manage; country-collection badges count foreign countries only, tiered ladders show just your next goal (no redundant 3/5, 3/10 stacking), and each unlocked badge shows the **flag + country where you earned it** on its unlock line (where a single place applies). **Click any badge** to open its own drill-down: its status, the full ladder progression for tiered badges (each level with a ✓ or its tally, your current one highlighted), and the countries/continents that count toward it — each a clickable chip through to that country. An **Alle · Fullførte · Gjenstår** filter lets you show all badges, just the earned ones, or just what's left to go (a to-do list with progress bars). Click a flag chip to open that country's drill-down — a single stat grid (løp, distanse, and **per-country records**: lengste løp, raskeste tempo skipping flagged outliers, mest høyde), a compact meta block below it with the **date range** (📅) and the **ute/inne split** (🏃/⚙️, always shown — "Alt utendørs" when the country isn't mixed), a **"Teller mot"** list of the badges that country counts toward — gold ✓ = unlocked *here*, green ✓ = unlocked (this country counts, another tipped it), grey tally = in progress, with a small legend for the two checkmark colors — and a free-text **memory/note** for the place (📝) — the note is the only thing you type; everything else is derived. Empty-`land` runs count as Norway (so only abroad runs need the Land field set)

### Session log (Treningslogg)
- Full sortable table — click any column header to sort
- **Sleep column** colour-coded at a glance: red `< 6h` · yellow `6–7h` · green `≥ 7h`
- **Høyde column** shows elevation in metres for outdoor runs and incline % for treadmill runs
- **RPE column** shows effort rating 1–10 in colour (green ≤3 · amber ≤6 · orange ≤8 · red 10); hidden on mobile
- **📋 icon** shown in the session name column when a workout description exists — hover to preview; **📝 icon** shown when a note exists — hover to preview
- **Responsive columns:** > 1600px shows everything; ≤ 1600px hides only Uke and Sko (keeps Mål km, Varighet, ♥ Topp, Søvn, Høyde, RPE — tested on 14" HiDPI laptop at 150% scaling = 1536px CSS viewport); ≤ 900px also hides Mål km, Varighet, ♥ Topp, Søvn; ≤ 600px additionally hides Navn and Plan — all fields accessible via edit form
- Filter by date range, session type, run type (outdoor/treadmill), and shoe
- Edit or delete any row
- **Export for AI chat** — checkbox column to select one or more sessions; **Kopier valgte** copies selected rows, **Kopier alle filtrerte** copies the full filtered view, **Last ned TSV** downloads as a file; single header row at the top, then one block per session: `=== YYYY-MM-DD | Øktnavn | dist km ===` header, optional `[Øktbeskrivelse]` block (workout plan/structure), note text (if any), then the data row; blocks separated by blank lines

### Planning (Planlegging)
- **Yearly goals (Mål)** — set a km target per year, tracked on the dashboard; ✏️ prefills the inputs for quick editing (re-adding a year overwrites it in place)
- **Hendelser** — events (Plan / Løp/Race / Sykdom / Ferie / Deload / Taper / Annet) shown as vertical markers on the charts; events with an end date render as spans — anomaly periods (Sykdom/Ferie/Deload/Taper/Annet) get a shaded fill, while Plan events draw start/end boundary lines only (a multi-week plan fill would tint the whole chart); the Hendelser chart toggle defaults off on small screens where the markers crowd the charts; Plan events can carry a total-km target (headline metric — steadier than weekly, since deload/taper weeks legitimately vary) plus optional weekly km/run targets, and drive the Treningsblokker cards; ✏️ opens the event in the form for in-place editing (e.g. adding an end date after the fact) — the button flips to "Lagre endringer" with an Avbryt escape
- **Sko** — manage shoe list with km totals; **Pensjonér** a shoe to hide it from the form dropdown while keeping historical data; **Aktiver** restores it; used in the log filter and form dropdown
- **Løp & Races** — lists all race events with matched session stats

### Settings (Innstillinger)
- **Profil & Puls** — max HR, resting HR, 5 zone boundaries; auto-calculate zones from max HR, or import your real boundaries directly from Strava *(requires Strava connection)*; zone boundaries drive HR zone analysis in training block drill-downs, Easy run Zone 2 compliance insights, and the Zone 2 efficiency filter
- **Beste innsats** — manually enter GPS-derived best effort times (400 m, 1 km, 5 km, 10 km, 15 km, halvmaraton, maraton) shown in compact mm:ss format, or sync them automatically from your full Strava history *(requires Strava connection; manual entry covers treadmill/manual PRs Strava can't)* — a full historical scan runs in rate-limit-safe batches and shows a review-before-applying comparison; these override Riegel estimates in the Ytelseskurve
- **Strava** — connect via OAuth to enable the Hent fra Strava form helper, zone import, and Beste innsats sync; requires a small Cloudflare Worker for the OAuth token exchange (Strava's API needs a client secret that can't live in browser code) — see [worker/README.md](worker/README.md) for deploy steps, entirely through Cloudflare's dashboard with no local tooling required; paste your Client ID and the Worker's URL, then click "Koble til Strava"
- **Treningsrytme** — km-grense and løp-grense per week used to compute the consistency score
- **Egendefinerte lister** — add your own session types and training plans; they appear in the form and filter dropdowns alongside the built-in ones (which stay fixed), and can be removed again when unused
- **Datafil** — open, create, download, or clear all data; **Lokale sikkerhetskopier** — automatic daily snapshots stored in browser IndexedDB (last 7 days), with one-click restore. A snapshot is also taken right before a clear-all, so that is recoverable too
- **Google Drive** — connect once via OAuth (PKCE flow); paste your Client ID and Client Secret from Google Cloud Console, click "Koble til", and data syncs silently on every save; connection persists across page reloads via a stored refresh token; Drive takes priority over the local file when connected — the local file status and sync indicator are hidden, only the ☁ Drive indicator is shown (and **Innstillinger → Datafil** reads «Synkroniseres via Google Drive»)

---

## Getting started

Open `puls.html` in your browser — no install needed. Or use the hosted version at **[psvadev.github.io/running/puls.html](https://psvadev.github.io/running/puls.html)** (navigating to the root redirects automatically). A small footer at the bottom of the page shows the currently deployed commit (fetched live from GitHub, with the last known version cached locally so it survives API hiccups), so you can confirm you're on the latest version.

First-time users see a short in-app welcome message on the logging form explaining the save flow — it disappears automatically after your first session is logged.

### First time (no existing data)

1. Add a session in **➕ Legg til økt** and click **Lagre økt**
2. A save dialog appears automatically — pick a folder and name (default: `puls.json`)
3. All future saves happen automatically in the background

(**⚙️ Innstillinger → ✨ Ny fil** also works if you prefer to create the data file before logging anything.)

### Loading an existing JSON file

1. Go to **⚙️ Innstillinger** → click **📂 Åpne fil**
2. Select your `puls.json` — data loads immediately across all tabs
3. The app remembers the file; next time you open it a one-click prompt restores access without re-picking

### Google Drive sync (optional, cross-device)

1. Go to **⚙️ Innstillinger** → **Google Drive**
2. Paste your **Client ID** and **Client Secret** (from [Google Cloud Console](https://console.cloud.google.com/) → Credentials → your OAuth 2.0 client)
3. Click **Koble til Google Drive** — you are redirected to Google sign-in and back
4. A `puls.json` file is created in your Drive (or the existing one is loaded)
5. Every subsequent save syncs automatically — no further clicks needed

The ☁ Drive indicator in the top bar turns green when connected. Data is cached locally so the app loads instantly on reload without waiting for Drive. On every page load the app silently re-fetches from Drive in the background, so changes from other devices appear automatically.

When Drive is active, the local file status and sync indicator are hidden — the Drive indicator is the only status shown. If you manually open a local file via Settings, both reappear alongside Drive sync.

If you open the app on a new device, repeat steps 1–3 once; the same Drive file is used.

**Requirements:**
- The app must be served over HTTP — either `python -m http.server 8080` locally or a hosted URL (GitHub Pages etc.). Opening `puls.html` directly as a `file://` URL will not work for Drive sync (OAuth requires an HTTP redirect URI).
- The redirect URI must be registered under *Authorized redirect URIs* in Google Cloud Console. Add both if using locally and on GitHub Pages:
  - `http://localhost:8080/puls.html`
  - `https://<your-username>.github.io/<repo>/puls.html`

Opening `puls.html` directly as a local file still works fully for offline use — only the Drive sync feature requires HTTP.

---

### Strava integration (optional)

1. Register a Strava API application at [strava.com/settings/api](https://www.strava.com/settings/api) — copy the **Client ID** and **Client Secret**
2. Deploy the OAuth token-exchange Worker — see [worker/README.md](worker/README.md) for full steps; works entirely through Cloudflare's dashboard, no local tooling required
3. Go to **⚙️ Innstillinger → Strava**, paste in your **Client ID** and the Worker's URL, then click **Koble til Strava**
4. Once connected:
   - **Hent fra Strava** appears in the logging form to pull in distance/duration/HR/pace/elevation/calories from a recent run, plus the Runna workout description if Runna pushed one to that activity
   - **Fra Strava** appears next to the zone auto-calc button in Profil & Puls
   - **Synkroniser fra Strava** appears in Beste innsats to pull your all-time best efforts

The Client Secret never leaves the Worker — only the Client ID and Worker URL are stored (in localStorage, same as Google Drive's credentials).

---

## Firefox & Safari

Firefox and Safari do not support the File System Access API, so local auto-save is unavailable. **Google Drive sync is the recommended alternative** — it works fully in both since it uses standard `fetch()` calls, not the File System Access API. Serve the app over HTTP and follow the [Google Drive sync](#google-drive-sync-optional-cross-device) setup above.

Without Drive sync:

- Load data: **⚙️ Innstillinger** → **📂 Åpne fil** (standard file input)
- Save data: **⚙️ Innstillinger** → **⬇️ Last ned** after each session to download the updated JSON
- Re-open the downloaded file next time to continue where you left off
- In this mode the save indicator reads **"Kun i nettleser — husk Last ned"** as a persistent reminder: your data is only in the browser's cache until you download it, so clearing browser data without downloading first would lose it

---

## Stack

Single `.html` file — no build step, no framework, no install.

- [Chart.js 4.4.0](https://www.chartjs.org/) — charts
- File System Access API — local file read/write (Edge/Chrome)
- IndexedDB — persists the file handle across page reloads so the file re-attaches automatically; also stores automatic daily local backups (last 7 days, one-click restore)
- Google Drive API (via fetch) + OAuth 2.0 PKCE — optional cross-device sync; refresh token stored in localStorage for silent reconnect
- Strava API (via fetch) + OAuth 2.0 — optional form-fill helper, zone import, and best-efforts sync; token exchange handled by a small Cloudflare Worker (see `worker/`)

Data semantics (field meanings, measurement caveats, what can and can't be compared) are documented in [DATA.md](DATA.md) — useful companion when feeding the TSV export to an AI chat for analysis.
