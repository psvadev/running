"""Tempo ↔ km/t converter (Planlegging). (2026-08-06)

Standalone, not in run_all.py (needs Playwright + WebKit):
    python tests/test_paceconv.py

Pure arithmetic, so the assertions are hand-computable anchors — 6:00 = 10,0 km/t exactly,
7:05 = 8,47 → 8,5, 7:30 = 8,0 exactly — plus the round-trip property and the two-way binding.
"""
import pathlib, sys, tempfile
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

# Relative to this file, not the repo checkout path — CI clones somewhere else entirely.
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


with sync_playwright() as p:
    b = p.webkit.launch()
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(APP)
    pg.evaluate("""() => localStorage.setItem('lpl_cache', JSON.stringify({
        sessions:[{id:'s',dato:'2026-08-01',uke:'2026-31',oktnavn:'x',okttype:'Easy',
                   treningsplan:'Runna',varighet:1800,distanse:5,soner:[0,0,0,0,0]}],
        shoes:[], goals:{}, events:[], settings:{zones:[]}, lastUpdated:'' }))""")
    pg.goto(APP)
    pg.evaluate("() => switchTab('plan')")
    pg.wait_for_timeout(300)

    # ---- pace -> km/t, anchors anyone can verify by hand
    print("== pace → km/t ==")
    for pace, want in [("6:00", "10,0"), ("7:30", "8,0"), ("7:05", "8,5"),
                       ("5:00", "12,0"), ("9:00", "6,7"), ("4:30", "13,3")]:
        pg.fill("#pcPace", pace)
        pg.wait_for_timeout(60)
        check(f"{pace} /km", pg.input_value("#pcKmh"), want)

    # ---- km/t -> pace
    print("== km/t → pace ==")
    for kmh, want in [("10", "6:00"), ("8", "7:30"), ("8,5", "7:04"),
                      ("12", "5:00"), ("6,7", "8:57")]:
        pg.fill("#pcKmh", kmh)
        pg.wait_for_timeout(60)
        check(f"{kmh} km/t", pg.input_value("#pcPace"), want)

    print("== both separators accepted ==")
    pg.fill("#pcKmh", "8.5")
    pg.wait_for_timeout(60)
    check("a period works like a comma", pg.input_value("#pcPace"), "7:04")

    # ---- Why there is no "nearest settable step" hint on the card.
    # A treadmill accepts 0.1 km/t, and pace = 3600/speed, so a FIXED speed step is worth
    # progressively MORE pace the slower you go: ~1 s/km at 12 km/t, ~12 s/km at 5.5 km/t.
    # The bound therefore has to be stated per range, not as one number (an earlier "~3 s/km
    # worst case" claim was measured only over 6:00-9:00 and does not hold to 12:00).
    # It stays negligible across everything he RUNS; it only grows where he walks, and 5 s/km
    # on a walk break is meaningless.
    # The honest measure is RELATIVE, not absolute: 5 s/km means something different at 5:00 than at
    # 12:00. In absolute terms the error grows with pace (~3.3 s/km worst while running, ~5.5 s/km at
    # 12:00) purely because 3600/speed steepens — but as a share of the pace it is flat and tiny.
    print("== rounding to one decimal is under 1 % of the pace, everywhere ==")
    err = pg.evaluate("""() => {
      let absWorst = 0, relWorst = 0;
      for (const s of PaceConv.rows()) {
        const set = Math.round(PaceConv.kmhFromPace(s) * 10) / 10;   // what you can dial in
        const d = Math.abs(3600 / set - s);
        absWorst = Math.max(absWorst, d);
        relWorst = Math.max(relWorst, d / s);
      }
      return { abs: +absWorst.toFixed(1), rel: +(relWorst * 100).toFixed(2) };
    }""")
    check(f"worst relative error is under 1 % ({err['rel']} %, {err['abs']} s/km absolute)",
          err["rel"] < 1, True)

    print("== round trip is stable ==")
    rt = pg.evaluate("""() => PaceConv.rows().filter(s => {
      const k = Math.round(PaceConv.kmhFromPace(s) * 10) / 10;
      return Math.abs(PaceConv.paceFromKmh(k) - s) > 6;
    })""")
    check("no row drifts more than 6 s through a round trip", rt, [])

    # ---- the table
    print("== reference table ==")
    rows = pg.locator("#pcTable .pc-row")
    check("row count", rows.count(), 25)
    first = rows.first.inner_text().split("\n")
    last = rows.last.inner_text().split("\n")
    check("starts at 4:30", first[0], "4:30")
    check("ends at 12:00", last[0], "12:00")
    check("step is 0:15 in the running range",
          rows.nth(1).inner_text().split("\n")[0], "4:45")
    # 9:00 is row index 18; the next must be 9:30, not 9:15
    check("step coarsens to 0:30 below 9:00", rows.nth(18).inner_text().split("\n")[0], "9:00")
    check("...next row is 9:30", rows.nth(19).inner_text().split("\n")[0], "9:30")

    print("== column legend ==")
    leg = pg.locator(".pc-legend")
    check("legend present", leg.count(), 1)
    legtxt = " ".join(leg.inner_text().split())
    check("names both units", ("min/km" in legtxt and "km/t" in legtxt), True)
    check("carries both icons", ("⏱" in legtxt and "⚡" in legtxt), True)
    # It must sit ABOVE the multicol flow, not inside it — inside, a header lands at the top of the
    # first column only and never repeats. Left edges align so it reads as that table's header.
    geo = pg.evaluate("""() => {
      const L = document.querySelector('.pc-legend').getBoundingClientRect();
      const T = document.getElementById('pcTable').getBoundingClientRect();
      return { sameLeft: Math.abs(L.left - T.left) < 8, above: L.bottom <= T.top + 1,
               inside: !!document.querySelector('#pcTable .pc-legend') };
    }""")
    check("legend is outside the table flow", geo["inside"], False)
    check("legend sits above the table", geo["above"], True)
    check("legend aligns with the table's left edge", geo["sameLeft"], True)
    check("input labels carry the same icons",
          [t.strip().split("\n")[0].strip() for t in pg.locator(".pc-field").all_inner_texts()],
          ["⏱️ Tempo", "⚡ Fart"])
    # Not on every row: emoji cannot be muted, so 25 rows x 2 would shout over the numbers.
    check("no icons repeated in the rows", pg.locator("#pcTable .pc-row").first.inner_text().count("⏱"), 0)

    print("== nearest row highlights ==")
    pg.fill("#pcPace", "7:05")
    pg.wait_for_timeout(60)
    check("one row highlighted", pg.locator("#pcTable .pc-hit").count(), 1)
    check("7:05 lights the 7:00 row", pg.locator("#pcTable .pc-hit .pc-p").inner_text(), "7:00")
    pg.fill("#pcPace", "7:30")
    pg.wait_for_timeout(60)
    check("an exact row lights itself", pg.locator("#pcTable .pc-hit .pc-p").inner_text(), "7:30")
    pg.fill("#pcPace", "2:00")     # far outside the table
    pg.wait_for_timeout(60)
    check("out-of-range lights nothing", pg.locator("#pcTable .pc-hit").count(), 0)
    pg.fill("#pcPace", "")
    pg.wait_for_timeout(60)
    check("clearing empties the other field", pg.input_value("#pcKmh"), "")
    check("clearing removes the highlight", pg.locator("#pcTable .pc-hit").count(), 0)

    print("== junk input is inert ==")
    for junk in ["abc", ":", "-5"]:
        pg.fill("#pcPace", junk)
        pg.wait_for_timeout(60)
        check(f"{junk!r} produces no speed", pg.input_value("#pcKmh"), "")

    print("== reads nothing from Store ==")
    indep = pg.evaluate("""() => {
      const before = document.getElementById('pcTable').innerHTML;
      const keep = Store.data.sessions;
      Store.data.sessions = [];
      PaceConv.render(0);
      const after = document.getElementById('pcTable').innerHTML;
      Store.data.sessions = keep;
      return before === after;
    }""")
    check("table is identical with no sessions at all", indep, True)

    # ---- mobile
    print("== mobile 402px ==")
    pg.set_viewport_size({"width": 402, "height": 900})
    pg.wait_for_timeout(200)
    over = pg.evaluate("""() => {
      const card = document.getElementById('pcTable').closest('.card');
      const bad = [];
      card.querySelectorAll('div,span,input,label').forEach(el => {
        if (el.scrollWidth > el.clientWidth + 1 && el.clientWidth > 0) bad.push(el.className);
      });
      return { bad, right: card.getBoundingClientRect().right, docW: document.documentElement.clientWidth };
    }""")
    check("nothing clipped", over["bad"], [])
    check("card inside the viewport", over["right"] <= over["docW"] + 1, True)
    # Debug aid only — nothing above asserts on it. Temp dir so a capture can never land in the
    # repo, where the blanket *.png ignore is the only thing standing between it and a commit.
    pg.screenshot(path=str(pathlib.Path(tempfile.gettempdir()) / "paceconv_402.png"),
                  clip={"x": 0, "y": 0, "width": 402, "height": 700})
    check("no page errors", errs, [])
    pg.close()
    b.close()

print(f"\n{passed}/{passed+failed} passed" + ("" if not failed else f"  ({failed} FAILED)"))
sys.exit(1 if failed else 0)
