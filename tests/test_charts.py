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

The fixture carries one week per verdict band plus one deliberately untargeted week, so rule 1 and
all four bullet colours are exercised together.

No local data file exists; every session is synthesised in-page.
"""
import pathlib, sys, tempfile
sys.stdout.reconfigure(encoding="utf-8")
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


# Two weeks with targets, one without — so the overlay must draw a GAP, not a zero.
SEED = """() => {
  const run = (id, dato, uke, distanse, mal) => ({
    id, dato, uke, oktnavn:'Tur', okttype:'Easy', treningsplan:'Runna',
    løpetype:'utendors', distanse, varighet: distanse*360, tempo:360,
    soner:[0,10,20,0,0], malDistanse: mal,
  });
  localStorage.setItem('lpl_cache', JSON.stringify({
    sessions:[
      run('a','2026-08-03','2026-32',10,12), run('b','2026-08-05','2026-32',8,8),  // 18/20 = 90%  near
      run('c','2026-08-10','2026-33',15,12),                                       // 15/12 = 125% over
      run('d','2026-08-17','2026-34',9,null),                                      // no target at all
      run('e','2026-08-24','2026-35',10,10),                                       // 10/10 = 100% reached
      run('f','2026-08-31','2026-36',5,10),                                        //  5/10 = 50%  under
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
    check("actual bars unchanged", ds[0]["d"], ["18.00", "15.00", "9.00", "10.00", "5.00"])

    # The verdict is carried by the BULLETS. Bars stay uniform — colouring them would collide with
    # this chart's default blue and make an untargeted week look like one that beat its target.
    pts = pg.evaluate("() => Charts.weeklyDist.data.datasets[1].pointBackgroundColor")
    check("90 % → amber (near)", pts[0], "rgba(240,192,80,1)")
    check("125 % → blue (over)", pts[1], "rgba(108,143,255,1)")
    check("⚠️ no target → transparent bullet, not a coloured verdict", pts[2], "transparent")
    check("100 % → green (reached)", pts[3], "rgba(75,190,120,1)")
    check("50 % → red (under)", pts[4], "rgba(224,85,85,1)")
    check("every bullet gets a rim so 'over' stays visible on the bar",
          pg.evaluate("() => Charts.weeklyDist.data.datasets[1].pointBorderColor"), "#e8eaf0")
    check("bars are still one uniform colour",
          pg.evaluate("() => typeof Charts.weeklyDist.data.datasets[0].backgroundColor"), "string")
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

    print("== the overlay is forced off on load ==")
    # NOT tested by "tick it, reload, assert false" — that passes VACUOUSLY here, because WebKit
    # does not restore form state in the first place. Chromium does, which is why the box survived
    # F5 in Edge but nowhere else. So prove the forcing directly: load a copy whose markup already
    # says `checked` and assert init cleared it. Without the fix this stays ticked and the overlay
    # renders unasked.
    src = pathlib.Path(__file__).resolve().parent.parent / "puls.html"
    html = src.read_text(encoding="utf-8")
    marker = '<input type="checkbox" id="distShowTarget">'
    assert html.count(marker) == 1, "checkbox markup moved — update this test"
    # Written to the SYSTEM temp dir, never beside puls.html: a run killed between write and unlink
    # would otherwise leave a stray .html in a public repo folder. puls.html is self-contained, so a
    # copy runs correctly from anywhere.
    tmp = pathlib.Path(tempfile.gettempdir()) / "_charts_checked_probe.html"
    tmp.write_text(html.replace(marker, marker[:-1] + " checked>"), encoding="utf-8")
    try:
        pg.goto(tmp.as_uri()); pg.wait_for_timeout(800)
        pg.evaluate("() => switchTab('dash')"); pg.wait_for_timeout(600)
        check("a pre-checked box is cleared by init",
              pg.evaluate("() => document.getElementById('distShowTarget').checked"), False)
        check("...so no overlay dataset is drawn unasked",
              pg.evaluate("() => Charts.weeklyDist.data.datasets.length"), 1)
    finally:
        tmp.unlink(missing_ok=True)

    pg.goto(APP); pg.wait_for_timeout(800)
    pg.evaluate("() => switchTab('dash')"); pg.wait_for_timeout(600)

    print("== 402 px ==")
    # POLL, don't sleep-and-hope. A fixed wait here failed ~1 run in 4: the Nullstill above kicks off
    # a full renderDashboard, and Chart.js canvases can still be mid-resize when the viewport changes,
    # so the page transiently measures wider than the viewport. Probed it — the steady state is clean
    # at every sample from 250 ms on, and the widest element (#weeklyTable, 450 px) lives inside its
    # own overflow-x:auto card, so it never pushes the page.
    # This still fails on a REAL overflow: that never settles, so the loop just runs out.
    pg.set_viewport_size({"width": 402, "height": 900})
    fits = False
    for _ in range(20):
        pg.wait_for_timeout(150)
        if pg.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1"):
            fits = True
            break
    check("no horizontal overflow (settled)", fits, True)

    check("no page errors", errs, [])
    b.close()

print(f"\n{passed}/{passed + failed} passed" + (f"  ({failed} FAILED)" if failed else ""))
sys.exit(1 if failed else 0)
