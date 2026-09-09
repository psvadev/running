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

    # ── Every hand-placed field looks and behaves like a .form-group one (2026-09-08) ───────────
    # Same disease this file already exists for: one rule written in several places. 19 fields
    # outside .form-group repeated its six paint properties inline — and had ALREADY drifted, having
    # copied the paint but not :focus or the transition, so they were the only fields in the app with
    # no accent border when clicked into. They now carry `.inp`, which shares the declaration.
    #
    # ⚠️ Read the focus colour AFTER the .15s border-color transition. Reading it immediately returns
    # the mid-transition value — which is the start colour — and makes a WORKING field look broken.
    # That is how the first version of this probe "proved" .form-group had no focus style either.
    print("== every field shares one appearance ==")
    pg = b.new_page(viewport={"width": 1400, "height": 900})
    ferr = []
    pg.on("pageerror", lambda e: ferr.append(str(e)))
    pg.goto(APP)
    pg.wait_for_timeout(500)

    def field(sel, tab):
        pg.evaluate(f"() => switchTab('{tab}')")
        pg.wait_for_timeout(200)
        base = pg.evaluate("""sel => { const c = getComputedStyle(document.querySelector(sel));
            return [c.borderColor, c.padding, c.fontSize]; }""", sel)
        pg.focus(sel)
        pg.wait_for_timeout(400)          # let the .15s transition finish — see the warning above
        return base + [pg.evaluate(
            "sel => getComputedStyle(document.querySelector(sel)).borderColor", sel)]

    ref = field("#fDistanse", "form")                    # inside .form-group — the reference
    check("control: the reference field highlights on focus", ref[0] != ref[3], True)
    check("...to the accent colour", ref[3], "rgb(108, 143, 255)")
    for sel, tab in (("#newEvtRunTarget", "plan"), ("#newCustomOkttype", "settings"),
                     ("#newEvtType", "plan"), ("#newGoalYear", "plan")):
        check(f"{sel} matches the reference (paint + focus)", field(sel, tab), ref)
    # Sizing must NOT be equalised: these fields are laid out by hand and keep their own widths.
    # ⚠️ Each is measured while ITS OWN tab is active. A field in a hidden panel measures 0 px wide,
    # which the first version of this check reported as a width regression — it was reading the
    # settings field with the plan tab open.
    def width(field_id, tab):
        pg.evaluate(f"() => switchTab('{tab}')")
        pg.wait_for_timeout(200)
        return pg.evaluate(
            "id => Math.round(document.getElementById(id).getBoundingClientRect().width)", field_id)
    check("...while keeping their own widths",
          [width('newGoalYear', 'plan'), width('newEvtRunTarget', 'plan'),
           width('newCustomOkttype', 'settings')], [90, 200, 340])
    # ⚠️ #newEvtDate carries NO inline width, so it is the only one a stray `width:100%` on .inp could
    # actually stretch — the others' inline widths outrank a class rule and would hide the mistake.
    # Added after a falsification (adding .inp to the width:100% rule) passed every check above.
    check("...and a field with no inline width keeps its intrinsic size",
          width('newEvtDate', 'plan'), 168)
    # Small muted text: one class, not 64 inline copies in two property orders.
    small = pg.evaluate("""() => {
        const cls = [...document.querySelectorAll('.muted-sm')];
        const c = cls.length ? getComputedStyle(cls[0]) : null;
        return { n: cls.length, font: c && c.fontSize, color: c && c.color,
                 // Anything re-introducing the pair inline, whichever order it is written in.
                 inline: document.querySelectorAll(
                     '[style*="font-size:12px"][style*="var(--muted)"]').length }; }""")
    # Control first: the absence check below is worthless if nothing carries the class at all.
    check("control: the muted-sm class is actually in use", small["n"] > 20, True)
    check("...and renders 12px muted", [small["font"], small["color"]],
          ["12px", "rgb(120, 128, 160)"])
    check("no element re-introduces the pair inline", small["inline"], 0)
    check("no field page errors", ferr, [])
    pg.close()

    # ── The ranges the fields declare are now enforced on save (2026-09-09) ─────────────────────
    # min/max were in the markup from the start and nothing ever read them: 900 bpm, -40 bpm,
    # -100 kcal and a negative Høydemeter all saved exactly as typed. Distanse was the only guarded
    # field, via the hand-written `s.distanse <= 0` check.
    #
    # ⚠️ Asserting "no session was saved" is only meaningful next to a case that DOES save — an
    # app that refused everything would pass every rejection check here. The control runs first.
    print("== declared ranges are enforced on save ==")
    pg = b.new_page(viewport={"width": 1400, "height": 900})
    verr, dialogs = [], []
    pg.on("pageerror", lambda e: verr.append(str(e)))
    pg.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))

    def attempt(field=None, value=None):
        """Fill a minimally valid session, optionally poison one field, click Lagre.
        Returns (sessions saved, alert text or '', the field's value afterwards)."""
        pg.goto(APP)
        pg.evaluate("() => localStorage.removeItem('lpl_cache')")   # or the previous save lingers
        pg.goto(APP)
        pg.wait_for_timeout(400)
        pg.evaluate("() => switchTab('form')")
        pg.wait_for_timeout(200)
        pg.evaluate("""() => {
            document.getElementById('fDistanse').value = '5';
            document.getElementById('fVarighet').removeAttribute('readonly');
            document.getElementById('fVarighet').value = '0:30:00';
        }""")
        if field:
            pg.evaluate("([i, v]) => { document.getElementById(i).value = v; }", [field, value])
        dialogs.clear()
        pg.click("#btnSaveSession")
        pg.wait_for_timeout(350)
        n = pg.evaluate("() => (Store.data.sessions || []).length")
        left = pg.evaluate("i => i ? document.getElementById(i).value : ''", field)
        return n, (dialogs[0] if dialogs else ""), left

    n, msg, _ = attempt()
    check("control: a valid session still saves", (n, msg), (1, ""))

    for field, value, word in (("fGjpuls", "900", "Gj.snittspuls"),
                               ("fGjpuls", "-40", "Gj.snittspuls"),
                               ("fToppuls", "900", "Toppuls"),
                               ("fKalorier", "-100", "Kalorier"),
                               ("fMalDistanse", "-3", "Mål distanse"),
                               ("fHoydeMeter", "-50", "Høydemeter")):
        n, msg, left = attempt(field, value)
        check(f"{field}={value} is refused", n, 0)
        check(f"...naming the field ({word})", word in msg, True)
        # The rule: reject visibly, never silently clear. A cleared field and a never-filled one
        # look identical, so the correction would have to start from nothing.
        check("...and the typed value is left in place", left, value)

    # Boundaries are INSIDE the range — an off-by-one here would reject 250 bpm, which is legal.
    n, msg, _ = attempt("fToppuls", "250")
    check("the max boundary itself is accepted", (n, msg), (1, ""))
    n, msg, _ = attempt("fKalorier", "0")
    check("the min boundary itself is accepted", (n, msg), (1, ""))

    check("no validation page errors", verr, [])
    pg.close()

    b.close()

print(f"\n{passed}/{passed+failed} passed" + ("" if not failed else f"  ({failed} FAILED)"))
sys.exit(1 if failed else 0)
