"""Stigning/Høydemeter are venue-exclusive — verify neither leaks onto the wrong venue. (2026-08-06)

Standalone, not in run_all.py (needs Playwright + WebKit):
    python tests/test_venue_fields.py

The bug this locks down: clear() seeded Stigning with the 1 % indoor default BEFORE the venue was
settled, and the venue change only ever *hid* the field, never emptied it. So logging an outdoor run
straight after a treadmill one saved a phantom `stigning: 1` on the outdoor session. The rule lived in
four places (clear, applyVenueForType, the #fLopetype onchange, the edit path); it now lives in
Form.syncVenueFields and the save is venue-guarded as well, so the invariant holds even if the form
misbehaves.
"""
import pathlib, sys
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


SEED = """
(lastVenue) => {
  const s = { id:'seed1', dato:'2026-08-01', uke:'2026-31', oktnavn:'Seed', okttype:'Easy',
              treningsplan:'Runna', varighet:1800, distanse:5, soner:[0,0,0,0,0] };
  s['l\\u00f8petype'] = lastVenue;
  localStorage.setItem('lpl_cache', JSON.stringify({
    sessions:[s], shoes:[], goals:{}, events:[], settings:{zones:[]},
    lastUpdated:new Date().toISOString() }));
}
"""


def boot(page, last_venue):
    page.goto(APP)
    page.evaluate(SEED, last_venue)
    page.goto(APP)
    page.evaluate("() => switchTab('form')")
    page.wait_for_timeout(300)


with sync_playwright() as p:
    b = p.webkit.launch()
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))

    # ---- 1. fresh form after a TREADMILL run: indoor, seeded 1 %
    print("== new form, last run was indoor ==")
    boot(pg, "treadmill")
    check("venue follows the last run", pg.input_value("#fLopetype"), "treadmill")
    check("stigning seeded to 1", pg.input_value("#fStigning"), "1")
    check("stigning visible", pg.locator("#stigningGroup").is_visible(), True)
    check("høydemeter hidden", pg.locator("#hoydeMeterGroup").is_visible(), False)

    # ---- 2. THE BUG: fresh form after an OUTDOOR run must not carry the indoor default
    print("== new form, last run was outdoor (the regression) ==")
    boot(pg, "utendors")
    check("venue follows the last run", pg.input_value("#fLopetype"), "utendors")
    check("stigning NOT seeded", pg.input_value("#fStigning"), "")
    check("stigning hidden", pg.locator("#stigningGroup").is_visible(), False)
    check("høydemeter visible", pg.locator("#hoydeMeterGroup").is_visible(), True)

    # and what actually gets saved
    saved = pg.evaluate("() => { const r = Form.read(); return { stigning: r.stigning, hoyde: r.hoydeMeter, venue: r['l\\u00f8petype'] }; }")
    check("outdoor session saves no stigning", saved["stigning"], None)
    check("outdoor session venue", saved["venue"], "utendors")

    # ---- 3. switching venue by hand keeps the pair exclusive, both ways
    print("== switching venue by hand ==")
    pg.select_option("#fLopetype", "treadmill")
    pg.wait_for_timeout(150)
    check("switching to indoor seeds 1 %", pg.input_value("#fStigning"), "1")
    # set the now-hidden outdoor field directly — Playwright cannot fill an invisible input, and
    # planting a stale value there is exactly the state the guard has to survive
    pg.evaluate("() => { document.getElementById('fHoydeMeter').value = '250'; }")
    pg.select_option("#fLopetype", "utendors")
    pg.wait_for_timeout(150)
    check("switching out empties stigning", pg.input_value("#fStigning"), "")
    pg.select_option("#fLopetype", "treadmill")
    pg.wait_for_timeout(150)
    check("switching back empties høydemeter", pg.input_value("#fHoydeMeter"), "")

    # ---- 4. the seed only fills a BLANK field, never overwrites a typed one
    print("== a typed value wins over the default ==")
    pg.fill("#fStigning", "3")
    pg.evaluate("() => Form.syncVenueFields(true)")   # re-sync without leaving the venue
    check("re-syncing indoor keeps a typed 3", pg.input_value("#fStigning"), "3")

    # ---- 5. the save guard holds even if the form is forced into a bad state
    print("== save guard is independent of the form ==")
    pg.evaluate("""() => {
      document.getElementById('fLopetype').value = 'utendors';
      document.getElementById('fStigning').value = '1';   // force the old bug's state
    }""")
    forced = pg.evaluate("() => { const r = Form.read(); return [r.stigning, r.hoydeMeter]; }")
    check("forced stigning is dropped on an outdoor save", forced[0], None)
    pg.evaluate("""() => {
      document.getElementById('fLopetype').value = 'treadmill';
      document.getElementById('fHoydeMeter').value = '250';
    }""")
    forced2 = pg.evaluate("() => { const r = Form.read(); return [r.stigning, r.hoydeMeter]; }")
    check("forced høydemeter is dropped on an indoor save", forced2[1], None)

    check("no page errors", errs, [])
    pg.close()
    b.close()

print(f"\n{passed}/{passed+failed} passed" + ("" if not failed else f"  ({failed} FAILED)"))
sys.exit(1 if failed else 0)
