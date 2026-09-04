"""Event markers on the dashboard charts — which charts draw them, and why.  (2026-09-04)

Standalone — NOT part of run_all.py, which is the fast no-browser gate. Run directly:
    python tests/test_event_markers.py      (needs Playwright + WebKit)

`eventLinesPlugin` is registered GLOBALLY (Chart.register), so it runs on every chart. Whether a
chart actually draws markers depends on `chart.data._rawLabels`, with a fallback to `chart.data.labels`
that only matches when those labels are raw ISO dates. Every chart doing `labels: keys.map(fmtKey)`
therefore opted OUT by accident — "Uke 36 '26" matches nothing. That was never a decision, and on
2026-09-04 Høydemeter and Run/walk ratio were opted back in by declaring `_rawLabels`/`_labelKind`.

⚠️ WHY THIS ASSERTS `$eventHits` AND NOT `_rawLabels`. Checking that the data field is set would be
this project's signature bug: it proves the input exists, not that anything was drawn. `$eventHits` is
reset each `afterDraw` and pushed once per marker group actually painted, so a non-empty array is
evidence the plugin ran, found events in range, and rendered them.

⚠️ THE POSITIVE CONTROL IS LOad-BEARING. `chartWeeklyDist` has carried markers since long before this
change. If the fixture were wrong — no events in the chart's date range, no analysed runs, markers
toggled off — every assertion below would read 0 and be misreported as "these charts have no markers".
The control proves the fixture can produce markers at all. Without it this file tests nothing.

`chartZones` is the negative control: it still formats its labels, so it must still draw none. It
catches the opposite failure — a change that switches markers on everywhere.

No local data file exists; every session is synthesised in-page.
"""
import pathlib, sys
sys.stdout.reconfigure(encoding="utf-8")   # æøå in labels
from playwright.sync_api import sync_playwright

APP = (pathlib.Path(__file__).resolve().parent.parent / "puls.html").as_uri()
passed = failed = 0


def check(name, got, want):
    global passed, failed
    if got == want:
        passed += 1
        print(f"  PASS {name}")
    else:
        failed += 1
        print(f"  FAIL {name}\n       got  {got!r}\n       want {want!r}")


# Outdoor runs carrying BOTH hoydeMeter (Høydemeter) and a *current* continuity analysis (Run/walk),
# so both cards render. Continuity must match CONTINUITY_ANALYSIS_VERSION / THRESHOLD_VERSION and the
# active thresholds or `_isCurrent` rejects it and the trend card stays hidden.
# Spans July + August so the Måned view has more than one column to place markers into.
SEED = """() => {
  const cont = () => ({
    version: 3, thresholdVersion: 2, walkMaxKmh: 7.0, runMinKmh: 7.5,
    movingTimeSeconds: 3000, runningTimeSeconds: 2800, walkingTimeSeconds: 100,
    unclassifiedTimeSeconds: 100, stoppedTimeSeconds: 0,
    runningRatio: 0.93, walkingRatio: 0.03, unclassifiedRatio: 0.04,
    runningDistanceMeters: 8000, walkingDistanceMeters: 200, unclassifiedDistanceMeters: 200,
    longestContinuousRunSeconds: 1200, longestContinuousRunMeters: 3100,
    runToWalkTransitions: 2, uphillWalkingTimeSeconds: 10, uphillWalkingDistanceMeters: 18,
    sampleCount: 3000, datakvalitet: 'høy', warnings: [],
  });
  const run = (id, dato, uke, km, hm) => ({
    id, dato, uke, oktnavn:'Tur', okttype:'Easy', treningsplan:'Runna',
    løpetype:'utendors', distanse:km, varighet:km*360, tempo:360, hoydeMeter:hm,
    soner:[0,600,1200,0,0], stravaId:'s'+id, stravaAnalysis:{ continuity: cont() },
  });
  localStorage.setItem('lpl_cache', JSON.stringify({
    sessions:[
      run('a','2026-07-13','2026-29',8,60),
      run('b','2026-07-20','2026-30',9,55),
      run('c','2026-08-03','2026-32',10,120),
      run('d','2026-08-17','2026-34',7,45),
      run('e','2026-08-31','2026-36',9,130),
    ],
    // One event in each month, so the Måned view exercises _labelKind on more than one column.
    // A wrong _labelKind is not hypothetical here: week and month keys are both "YYYY-NN", and
    // conflating them once put a January race on February.
    events:[
      { id:'e1', type:'deload',  date:'2026-08-17', title:'Deload' },
      { id:'e2', type:'race',    date:'2026-08-31', title:'Testløp' },
      { id:'e3', type:'vacation',date:'2026-07-20', title:'Ferie' },
    ],
    shoes:[], shoeDefaults:{}, goals:{}, plannedSessions:[],
    settings:{zones:[]}, lastUpdated:'' }));
}"""

# Markers actually painted on a canvas, by element id. Reset every afterDraw, pushed once per group.
HITS = """(id) => {
  const c = document.getElementById(id);
  return (c && c.$eventHits) ? c.$eventHits.length : -1;   // -1 = canvas absent / never drew
}"""

with sync_playwright() as p:
    b = p.webkit.launch()
    pg = b.new_page(viewport={"width": 1400, "height": 1000})   # >600px: markers default ON
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(APP)
    pg.evaluate(SEED)
    pg.reload()
    # The app opens on «Legg til økt», so every dashboard canvas is inside a hidden panel until
    # this runs — charts never draw and the toggles are unclickable.
    pg.evaluate("() => switchTab('dash')")
    pg.wait_for_timeout(900)

    # ── The control that makes every other assertion meaningful ───────────────────────────────────
    print("== fixture control ==")
    ctrl = pg.evaluate(HITS, "chartWeeklyDist")
    check("Ukentlig distanse draws markers (fixture is valid)", ctrl > 0, True)
    if ctrl <= 0:
        print("\n  ⚠️ CONTROL FAILED — the fixture produced no markers anywhere, so the results")
        print("     below say nothing about the two charts under test. Fix the fixture first.")

    print("== newly opted in (2026-09-04) ==")
    check("Høydemeter per uke draws markers", pg.evaluate(HITS, "chartElev") > 0, True)
    check("Run/walk ratio draws markers", pg.evaluate(HITS, "chartContTrend") > 0, True)

    # ── Negative control: markers must not have been switched on everywhere ───────────────────────
    print("== still deliberately without ==")
    check("Pulssoner still draws none", pg.evaluate(HITS, "chartZones"), 0)

    # ── Måned mode: the _labelKind path. Week and month keys are both "YYYY-NN". ──────────────────
    print("== måned mode (_labelKind) ==")
    pg.click("#elevToggleMaaned")
    pg.click("#contTrendToggleMaaned")
    pg.wait_for_timeout(500)
    check("Høydemeter keeps markers in Måned", pg.evaluate(HITS, "chartElev") > 0, True)
    check("Run/walk keeps markers in Måned", pg.evaluate(HITS, "chartContTrend") > 0, True)
    # Two months carry events, so a correct month mapping puts markers in two distinct columns.
    # A week/month mix-up collapses or misplaces them, which a bare count would not notice.
    spread = pg.evaluate("""() => {
      const c = document.getElementById('chartElev');
      const xs = (c.$eventHits || []).map(h => Math.round((h.x0 + h.x1) / 2));
      return new Set(xs).size;
    }""")
    check("...in two distinct columns, not collapsed", spread >= 2, True)

    pg.click("#elevToggleWeek")
    pg.click("#contTrendToggleWeek")
    pg.wait_for_timeout(400)

    # ── The toggle still governs both new charts ──────────────────────────────────────────────────
    print("== Hendelser checkbox ==")
    pg.uncheck("#chkEvents")
    pg.wait_for_timeout(600)
    check("unchecking clears Høydemeter markers", pg.evaluate(HITS, "chartElev"), 0)
    check("unchecking clears Run/walk markers", pg.evaluate(HITS, "chartContTrend"), 0)
    check("...and the pre-existing chart too", pg.evaluate(HITS, "chartWeeklyDist"), 0)
    pg.check("#chkEvents")
    pg.wait_for_timeout(600)
    check("re-checking restores them", pg.evaluate(HITS, "chartElev") > 0, True)

    check("no page errors", errs, [])
    pg.close()
    b.close()

print(f"\n{passed}/{passed+failed} passed" + ("" if not failed else f"  ({failed} FAILED)"))
sys.exit(1 if failed else 0)
