"""Mål km overlay on Ukentlig distanse, and the two cards it replaced.  (2026-08-25)

Standalone — NOT part of run_all.py, which is the fast no-browser gate. Run directly:
    python tests/test_charts.py           (needs Playwright + WebKit)

Treningskalender was removed (unused in practice) and "Plan vs faktisk — distanse" was folded into
Ukentlig distanse as an opt-in overlay: its bars were the SAME weekly kilometres this chart already
plotted, so only the dashed target line was ever unique.

NOTHING tested either card before, on any surface. What this pins is the two rules that are easy to
break silently and impossible to see in a screenshot:

  1. A WEEK WITH NO TARGET IS A GAP, NOT A ZERO. `null` makes Chart.js break the line, which reads
     as "nothing was planned". A 0 would draw the line to the floor and look like a missed week.
  2. THE OVERLAY IS WEEK-MODE ONLY, and that is correctness, not taste. Only weeks carrying a target
     contribute one, so a month where 2 of 4 weeks were planned sums to a half-size target while the
     bar shows the full month — it would read as "wildly over plan" when it is really missing data.

The fixture is built for rule 1: two weeks with targets and one deliberately without.

No local data file exists; every session is synthesised in-page.
"""
import pathlib, sys
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

APP = pathlib.Path(r"c:\temp\GitHub\running\puls.html").as_uri()
passed = failed = 0


def check(name, got, want):
    global passed, failed
    if got == want:
        passed += 1
        print(f"  PASS {name}")
    else:
        failed += 1
        print(f"  FAIL {name}\n       got  {got!r}\n       want {want!r}")


# Two weeks with targets, one without — so the overlay must draw a GAP, not a zero.
SEED = """() => {
  const run = (id, dato, uke, distanse, mal) => ({
    id, dato, uke, oktnavn:'Tur', okttype:'Easy', treningsplan:'Runna',
    løpetype:'utendors', distanse, varighet: distanse*360, tempo:360,
    soner:[0,10,20,0,0], malDistanse: mal,
  });
  localStorage.setItem('lpl_cache', JSON.stringify({
    sessions:[
      run('a','2026-08-03','2026-32',10,12), run('b','2026-08-05','2026-32',8,8),
      run('c','2026-08-10','2026-33',15,12),
      run('d','2026-08-17','2026-34',9,null),
    ],
    shoes:[], shoeDefaults:{}, goals:{}, events:[], plannedSessions:[],
    settings:{zones:[]}, lastUpdated:'' }));
}"""

with sync_playwright() as pw:
    b = pw.webkit.launch()
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("dialog", lambda d: d.accept())
    pg.goto(APP); pg.evaluate(SEED); pg.goto(APP)
    pg.wait_for_timeout(800)
    pg.evaluate("() => switchTab('dash')")
    pg.wait_for_timeout(700)

    print("== the two removed cards are gone ==")
    for sel, label in [("#heatmapCard", "Treningskalender card"),
                       ("#heatmapContainer", "heatmap container"),
                       ("#hmTooltip", "heatmap tooltip element"),
                       ("#planActualCard", "Plan vs faktisk card"),
                       ("#chartPlanActual", "Plan vs faktisk canvas")]:
        check(f"{label} absent", pg.evaluate(f"() => !!document.querySelector('{sel}')"), False)
    check("renderHeatmap is undefined",
          pg.evaluate("() => typeof renderHeatmap"), "undefined")
    check("no 'Treningskalender' text on the dashboard",
          "Treningskalender" in pg.locator("#panel-dash").inner_text(), False)
    check("no 'Plan vs faktisk' text on the dashboard",
          "Plan vs faktisk" in pg.locator("#panel-dash").inner_text(), False)

    print("== the weekly distance chart still works ==")
    check("chart exists", pg.evaluate("() => !!Charts.weeklyDist"), True)
    check("one dataset while the box is unchecked",
          pg.evaluate("() => Charts.weeklyDist.data.datasets.length"), 1)
    check("Mål km checkbox is offered (targets exist)",
          pg.evaluate("() => getComputedStyle(document.getElementById('distTargetWrap')).display"), "flex")

    print("== ticking Mål km adds the overlay ==")
    pg.check("#distShowTarget"); pg.wait_for_timeout(400)
    ds = pg.evaluate("() => Charts.weeklyDist.data.datasets.map(d => ({l:d.label, t:d.type, d:d.data}))")
    check("two datasets", len(ds), 2)
    check("overlay is a line named 'Mål km'", (ds[1]["l"], ds[1]["t"]), ("Mål km", "line"))
    check("wk32 target = 12+8 = 20", ds[1]["d"][0], 20)
    check("wk33 target = 12", ds[1]["d"][1], 12)
    check("⚠️ untargeted week is null (a GAP), not 0", ds[1]["d"][2], None)
    check("actual bars unchanged", ds[0]["d"], ["18.00", "15.00", "9.00"])
    check("legend shown only with the overlay",
          pg.evaluate("() => Charts.weeklyDist.options.plugins.legend.display"), True)

    print("== Måned mode hides it — summing partial targets would lie ==")
    pg.click("#distToggleMaaned"); pg.wait_for_timeout(400)
    check("checkbox hidden in month mode",
          pg.evaluate("() => getComputedStyle(document.getElementById('distTargetWrap')).display"), "none")
    check("no overlay dataset in month mode",
          pg.evaluate("() => Charts.weeklyDist.data.datasets.length"), 1)

    print("== Nullstill resets it ==")
    pg.click("#distToggleWeek"); pg.wait_for_timeout(300)
    pg.check("#distShowTarget"); pg.wait_for_timeout(300)
    pg.click("#btnDashReset"); pg.wait_for_timeout(600)
    check("checkbox cleared", pg.evaluate("() => document.getElementById('distShowTarget').checked"), False)
    check("back to one dataset", pg.evaluate("() => Charts.weeklyDist.data.datasets.length"), 1)

    print("== 402 px ==")
    pg.set_viewport_size({"width": 402, "height": 900}); pg.wait_for_timeout(500)
    check("no horizontal overflow",
          pg.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1"), True)

    check("no page errors", errs, [])
    b.close()

print(f"\n{passed}/{passed + failed} passed" + (f"  ({failed} FAILED)" if failed else ""))
sys.exit(1 if failed else 0)
