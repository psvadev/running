"""Verify the RPE field, which gained half-steps on 2026-08-20.  (first suite to cover it at all)

Standalone — NOT part of run_all.py, which is the fast no-browser gate. Run directly:
    python tests/test_rpe.py            (needs Playwright + WebKit)

Why this field is worth a suite despite being one <select>:

  1. THE READ WAS parseInt. Adding a 6.5 option without changing that would have stored 6 — the form
     would report "Lagret", the log would show 6, and nothing anywhere would say a value had been
     changed. That is the exact shape of every silent-data-loss bug the engineering audit found, so
     the round-trip is asserted on the STORE, not on the form.
  2. IT IS THE ONLY SUBJECTIVE FIELD. Everything else on the form is measured or derived, so a
     rounding here is unrecoverable — there is no stream to re-read it from.
  3. THE COLOUR BANDS ARE BOUNDARY-KEYED (rpeColor: <=3, <=6, <=8, else). Half-steps land BETWEEN
     the old boundaries for the first time, and 6.5 crossing into the harder band is a judgement the
     code makes silently.
  4. EDIT MUST RESELECT. A select can only show a value it has an <option> for; restoring 6.5 onto a
     dropdown that offered only whole numbers would fail to a blank field, which looks exactly like
     "never filled in".

No local data file exists; every session is synthesised in-page.
"""
import pathlib, sys
sys.stdout.reconfigure(encoding='utf-8')   # æøå in the labels
from playwright.sync_api import sync_playwright

APP = (pathlib.Path(__file__).resolve().parent.parent / "puls.html").as_uri()
passed = failed = 0

FREEZE = """
(() => {
  const R = Date;
  const fixed = new R(2026, 7, 18, 12, 0, 0).getTime();
  function F(...a) { return a.length ? new R(...a) : new R(fixed); }
  F.prototype = R.prototype; F.now = () => fixed; F.parse = R.parse; F.UTC = R.UTC;
  window.Date = F;
})();
"""


def check(name, got, want):
    global passed, failed
    if got == want:
        passed += 1
        print(f"  PASS {name}")
    else:
        failed += 1
        print(f"  FAIL {name}\n       got  {got!r}\n       want {want!r}")


SEED = """() => {
  localStorage.setItem('lpl_cache', JSON.stringify({
    sessions: [{ id:'a', dato:'2026-08-10', uke:'2026-33', oktnavn:'Tur', okttype:'Easy',
                 treningsplan:'Egentrening', løpetype:'utendors', distanse:5, varighet:1800,
                 tempo:360, soner:[0,0,0,0,0], rpe:6 }],
    shoes: [], goals: {}, events: [], plannedSessions: [], settings: { zones: [] },
    lastUpdated: '' }));
}"""

with sync_playwright() as pw:
    b = pw.webkit.launch()
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("dialog", lambda d: d.accept())
    pg.add_init_script(FREEZE)
    pg.goto(APP)
    pg.evaluate(SEED)
    pg.goto(APP)
    pg.wait_for_timeout(500)

    # ── 1. The scale itself ─────────────────────────────────────────────────────────────────
    print("== the dropdown offers 1–10 in half-steps ==")
    vals = pg.eval_on_selector_all('#fRpe option', "o => o.map(x => x.value).filter(Boolean)")
    want = [str(n / 2) if n % 2 else str(n // 2) for n in range(2, 21)]
    check("every half-step from 1 to 10, in order", vals, want)
    check("...which is 19 values", len(vals), 19)
    check("a blank option still leads", pg.eval_on_selector_all('#fRpe option', "o => o[0].value"), '')

    labels = pg.eval_on_selector_all('#fRpe option', "o => o.map(x => x.textContent)")
    check("whole numbers keep their anchor word", '6 — Tungt' in labels, True)
    check("...and the top of the scale", '10 — Maksimalt' in labels, True)
    check("half-steps are deliberately unnamed", '6.5' in labels, True)
    # ⚠️ The label and the log must spell the number the same way, or you pick one thing and read
    # another. The app uses a decimal POINT everywhere except the ACWR tile.
    check("...spelled with a point, like the rest of the app",
          any(',' in l for l in labels), False)

    # ── 2. ⚠️ THE ROUND-TRIP — asserted on the STORE, not the form ──────────────────────────
    # This is the check that would have failed on parseInt: the form would look right and the saved
    # number would be 6.
    print("== a half-step survives the save ==")
    pg.evaluate("() => switchTab('form')")
    pg.wait_for_timeout(300)
    pg.fill('#fDato', '2026-08-17')
    pg.fill('#fDistanse', '5')
    pg.fill('#fSone2', '0:30:00')      # Varighet is readonly — "auto fra soner"
    pg.select_option('#fRpe', '6.5')
    pg.click('#btnSaveSession')
    pg.wait_for_timeout(400)
    saved = pg.evaluate("() => (Store.data.sessions.find(s => s.dato === '2026-08-17') || {}).rpe")
    check("6.5 is stored as 6.5, not truncated to 6", saved, 6.5)
    check("...and it is a number, not a string", pg.evaluate(
        "() => typeof (Store.data.sessions.find(s => s.dato === '2026-08-17') || {}).rpe"), 'number')

    # ── 3. Edit reselects the half-step ─────────────────────────────────────────────────────
    print("== editing that session shows the value back ==")
    sid = pg.evaluate("() => Store.data.sessions.find(s => s.dato === '2026-08-17').id")
    pg.evaluate(f"() => Form.editSession('{sid}')")
    pg.wait_for_timeout(300)
    check("the dropdown reselects 6.5", pg.locator('#fRpe').input_value(), '6.5')
    check("...not a blank field, which reads as never-filled",
          pg.locator('#fRpe').input_value() == '', False)
    # cancelEdit(), NOT clear(): clear() empties every field but deliberately leaves `editId` set —
    # the app closes that hole by HIDING "Tøm skjema" while editing (puls.html ~5546), so the guard
    # lives in the button's visibility rather than in the function. Calling clear() here would leave
    # the next save bound to this session and silently overwrite it.
    pg.evaluate("() => Form.cancelEdit()")
    pg.wait_for_timeout(250)
    pg.evaluate("() => switchTab('form')")
    pg.wait_for_timeout(200)
    check("cancelling the edit unbinds the form", pg.evaluate("() => Form.editId"), None)

    # ── 4. Whole numbers still work, and a blank stays blank ────────────────────────────────
    print("== the existing whole-number values are untouched ==")
    check("the seeded whole number is still 6",
          pg.evaluate("() => Store.data.sessions.find(s => s.dato === '2026-08-10').rpe"), 6)
    pg.fill('#fDato', '2026-08-16')
    pg.fill('#fDistanse', '4')
    pg.fill('#fSone2', '0:24:00')
    pg.click('#btnSaveSession')
    pg.wait_for_timeout(400)
    check("no RPE picked stores null, not 0",
          pg.evaluate("() => (Store.data.sessions.find(s => s.dato === '2026-08-16') || {}).rpe"), None)

    # ── 5. The colour bands, which half-steps reach for the first time ──────────────────────
    # rpeColor is boundary-keyed (<=3, <=6, <=8, else). 6.5 is the first value that can fall on the
    # far side of a boundary its neighbour sits on, and the band change is silent.
    print("== half-steps land in the right colour band ==")
    band = pg.evaluate("""() => {
      const names = { 'var(--green)':'green', '#f0c050':'amber', '#e08040':'orange', '#e05555':'red' };
      const out = {};
      [3, 3.5, 6, 6.5, 8, 8.5, 10].forEach(n => { out[String(n)] = names[rpeColor(n)] || rpeColor(n); });
      return out;
    }""")
    check("3 is the top of green", band['3'], 'green')
    check("3.5 steps up to amber", band['3.5'], 'amber')
    check("6 is the top of amber", band['6'], 'amber')
    check("6.5 steps up to orange — 'tungt' is behind you", band['6.5'], 'orange')
    check("8 is the top of orange", band['8'], 'orange')
    check("8.5 steps up to red", band['8.5'], 'red')
    check("10 stays red", band['10'], 'red')

    # ── 6. It reaches the surfaces that print it ────────────────────────────────────────────
    print("== the log row and the detail panel print the half-step ==")
    pg.evaluate("() => switchTab('log')")
    pg.wait_for_timeout(500)
    row = pg.evaluate(r"""() => {
      const tr = [...document.querySelectorAll('#logBody tr')]
        .find(r => r.textContent.includes('2026-08-17') || r.textContent.includes('17.08'));
      return tr ? tr.innerText.replace(/\s+/g, ' ') : '<<no row>>';
    }""")
    check("the log row shows 6.5, not 6", '6.5' in row, True)

    pg.evaluate(f"() => DetailPanel.openSession('{sid}')")
    pg.wait_for_timeout(400)
    panel = pg.evaluate("() => (document.querySelector('#detailPanel, .detail-panel') || document.body).innerText")
    check("the detail panel shows 6.5/10", '6.5/10' in panel, True)

    check("no page errors", errs, [])
    b.close()

print(f"\n{passed}/{passed + failed} passed" + (f"  ({failed} FAILED)" if failed else ""))
sys.exit(1 if failed else 0)
