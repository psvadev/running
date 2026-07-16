# DATA.md — data semantics for puls.json

Field dictionary and caveats for the session data. Purpose: let any future session (human, Claude, or an AI chat fed the TSV export) reason correctly about this data without rediscovering its assumptions. Short and factual — architecture/dev context lives in HANDOFF.md (local).

## Session fields

| Field | Type | Semantics & caveats |
|---|---|---|
| `id` | string | Stable unique id; edits reuse it. |
| `dato` | `YYYY-MM-DD` | Local date (not UTC) — see `localISODate` helpers. |
| `uke` | `YYYY-WW` | ISO week, derived from `dato`. |
| `oktnavn` | string | Free text; often auto-generated as "{Treningsplan} {Økttype}". |
| `okttype` | string | One of the 7 core types (Easy, Steady, Long, Tempo, Intervaller, Test, Race) or a user-defined custom type. Only **Test/Race** anchor the Ytelseskurve and Formkurve. |
| `treningsplan` | string | Egentrening, Runna, or custom. |
| `varighet` | seconds | **Normally the sum of the five zone times** ("auto fra soner"). **Strava-imported sessions store Strava's `moving_time` instead**, which can differ slightly from the zone sum. Manually entered when "Uten pulsdata" is checked. |
| `distanse` | km (float) | Treadmill: belt-measured. Outdoor: GPS. These disagree systematically — see "Belt vs GPS" below. |
| `gjsnittspuls` / `toppuls` | bpm | Missing on some sessions. Known anomalies: **2026-06-24 HR is estimated from Apple Health** (not chest strap); **2026-04-17 and 2026-07-01 have no pulsdata at all**. Sessions without HR contribute **zero** to the zone-weighted load, PMC (CTL/ATL/TSB), and Belastning charts. |
| `soner` | `[s1..s5]` seconds | Time per pulse zone. Zone boundaries use **touching convention** (zone N max = zone N+1 min), matching Strava. |
| `kalorier` | int | From watch/Strava; not used in any computation. |
| `malDistanse` | km | The planned distance for the session. |
| `tempo` | sec/km | Auto-calculated from varighet/distanse. |
| `snittkmh` | km/h | Auto-calculated; feeds aerobic efficiency (`snittkmh / gjsnittspuls × 100`). |
| `stigning` | % (≤20) | **Treadmill incline only.** Usually 1 % — the standard outdoor-equivalence convention, so treadmill paces are already roughly outdoor-equivalent in energy cost. Not an elevation measurement. |
| `hoydeMeter` | m | **Outdoor elevation gain only** (mutually exclusive with `stigning`). Per-run totals are too coarse for grade-adjusted pace — do not attempt GAP from this. |
| `sko` | string | Shoe name; km per shoe aggregated for lifecycle tracking. |
| `løpetype` | `utendors` \| `treadmill` | Venue. Default `utendors`. |
| `sovn` | hours (decimal) | **Sleep the single night before the run — NOT a weekly average.** Can only measure acute effects, which are physiologically expected to be weak; chronic sleep debt is invisible in this data. 6.87 = 6 h 52 m. |
| `rpe` | 1–10 | Apple Fitness scale. **The field was added 2026-06-01; values before that (back to late April 2026) were backfilled from Apple Fitness** — contemporaneous recordings, not reconstructed memory. Sparse before late April 2026. |
| `beskrivelse` | string | Workout structure; auto-filled from Strava (Runna pushes its program text into Strava's description). |
| `notater` | string | Free-text session notes; carries the "why" for flagged sessions. |
| `utenforAnalyse` | bool? | Outlier flag ("Avvik"). `true` = excluded from **quality** analytics (trends, insights, quality charts, pace/distance records, Ytelseskurve/Formkurve anchors) but **kept** in all volume metrics (km totals, streaks, heatmap, load, PMC, blocks, goals). Absent = false. Exclusions are always visible (dimmed log row, detail-panel row, `[Avvik]` tag in exports). |
| `land` | ISO 3166-1 alpha-2? | Country the run took place in. **Absent/empty = Norway** (home default) — only filled for abroad runs. TSV exports the raw code (e.g. `SE`). Norwegian display names are derived at runtime via `Intl.DisplayNames`; unresolvable typed text is stored raw and shown without a flag. Not used in any computation — powers only the "Land løpt i" card. **Strava auto-fill:** `location_country` is Strava-deprecated (usually null), so import falls back to the activity **timezone** (`Asia/Manila` → PH) via a bundled tz-database zone→country lookup. **Abroad only** — a resolved `NO` (home) is deliberately left blank to keep the "empty = Norge" convention; unknown zone → blank too (never a wrong guess). |
| `stravaId` | string? | The Strava activity id this session was filled from. Set only on sessions populated via "Hent fra Strava" **from 2026-07 onward** — older and manually-entered sessions have none. Enables the edit-form "Oppdater fra Strava" button (re-pull the same activity by id). **Internal handle only** — not used in any computation and never shown in the log, session detail, or TSV export (lives in `puls.json` and a hidden form field). |

## Belt vs GPS — never merge these

- **Treadmill PRs** are belt-measured (Distanse-PR brackets include them).
- **Strava "Topp 3" best efforts** are GPS-measured, outdoor-only (Strava computes no best efforts for treadmill runs).
- Outdoor pace at the same HR reads consistently faster than treadmill — likely belt calibration, GPS error, and indoor heat/airflow, **not** gradient (the 1 % convention covers that). Treat the surfaces as separate populations; do not combine belt and GPS times in one ranking.

## Events (`Store.data.events`)

`{ id, date, type, endDate?, title }` — types: `plan`, `race`, `illness`, `vacation`, `deload`, `taper`, `personal`. `endDate` is **inclusive**. Plan events may carry `targetTotalKm` / `targetKmPerWeek` / `targetRunsPerWeek`.
Syk/Ferie/Deload/Taper events **explain gaps and dips in the volume charts** — check them before interpreting a drop as detraining. Treningsrytme treats runless weeks covered by `illness`/`vacation` as unavailable rather than failed.

## Other data stores

- `bestEfforts` — best-effort times (seconds) per distance; may be belt- or GPS-based (user-entered); overrides Riegel estimates in Ytelseskurve. Holds the *fastest* time per distance: the Strava sync only offers a value when it's faster than the stored one (or fills an empty slot), so a treadmill PR is never overwritten by a slower outdoor GPS time.
- `bestEffortsTop3` — Strava-scanned top-3 per distance `{t, d}`; GPS/outdoor only. The scan's `localStorage` buffer is **device-local** (not Drive-synced); only this committed field syncs. Commits **merge** (union, dedupe on `(t,d)`, fastest 3) into the existing set — never overwrite — so a sync on one device can't drop history scanned on another. Rebuild a depleted set via Innstillinger → "Skann hele historikken på nytt".
- `shoes` — `{ name, retirementKm?, retired? }`.
- `goals` — yearly km targets keyed by year.
- `countryNotes` — free-text memory per country `{ ISO: text }` (e.g. `{ "PH": "treadmill was in mph…" }`). The **one user-authored/persisted** Løpeatlas piece (everything else is derived); text only, no media. Edited/shown in the country drill-down (`DetailPanel.openLand`); a 📝 dot marks chips that have one. Absent = none; empty save deletes the key. Not used in any computation.
- **Løpeatlas** (travel stats + **37 fixed achievements** in 6 groups Milepæler/Land/Verdensdeler/Distanse/Omgivelser/Sesong, **plus dynamic per-year New Country Year stamps** — so the badge total grows over time) is **fully derived** from `sessions` (`land`/`dato`/`distanse`/`løpetype`/`okttype`/`hoydeMeter`) + `events` (`vacation` overlap for the Vacation Runner badge) via `computeAtlas()` — **nothing persisted**, no badge state, so editing an old run's date/country can shift derived unlock dates ("Sist låst opp"). Home = `ATLAS_HOME='NO'`; blank `land` = home. Country-collection tier badges (Passport/World Traveler/Frequent Flyer/Globetrotter) count foreign countries only; regional-explorer + continents + Nordic count all resolved incl. home via the static `CONTINENTS` map (6 inhabited; Antarctica excluded; Both Hemispheres uses a `SOUTHERN` hand-list); unresolvable `land` text still shows as a chip but has no continent. The two **Nordic** badges live under Verdensdeler (a near-home European sub-region — no standalone Norden group). Tiered **ladders** (`ATLAS_LADDERS`: foreign-country count, continents, Nordic, longest-single-run distance, cumulative km abroad `globe-*` 10→25→50→100→250, distinct outdoor-abroad countries `outdoor-*` 3→5→10, and single-run elevation gain abroad `hills`/`foreign-climber`/`foreign-summit` 50→200→500 m) show unlocked tiers + only the next locked one, so a beginner starts on an obtainable target that escalates once reached. Elevation tiers are **per single run** (the hilliest one foreign outdoor run), not cumulative — 500 m is a deliberate mountain-trip stretch. A few badges carry **dynamic** names/desc from the derived data: Multi-Year Traveler lists the actual years (`… i 2 kalenderår: 2025, 2026`). **New Country Year** is a set of **dynamically generated per-year badges** (not one static badge): one permanent stamp `New Country Year (YYYY)` for each calendar year you first ran in a **brand-new foreign country** (first-ever run in that country falls in that year), showing the year + unlocking country (`Nytt land i 2026: Sverige +N` if several that year) + its flag; the **current year always appears too**, as a locked objective until you discover somewhere new (`Løp i et nytt land i 2026`). Built in `computeAtlas` (grouping `foreignByFirst` by first-run year) and appended to `a.badges` — so past years never un-earn (fixing the old single-badge annual reset). Single-run/threshold badges also carry the **country where they were earned** (`country` ISO code in the badge object) and render a small flag + country name on the "Låst opp" line; continent-count (Continental/Global), cumulative-km (`globe-*`), Multi-Year, and New Country Year (already named in its desc) deliberately carry no flag.

## Computation conventions

- Riegel exponent **1.06** for all equivalent-time math (`t2 = t1 × (d2/d1)^1.06`).
- Zone-weighted load = `Σ(soner[i] × [1,2,3,4,5]) / 60` (weighted minutes). PMC: CTL 42-day / ATL 7-day exponential averages of daily load; TSB = CTL − ATL.
- All "today"/window boundaries use local dates, never UTC.
