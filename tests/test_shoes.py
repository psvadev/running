"""Verify shoe wear — one `shoeWear` definition behind three surfaces.  (2026-08-21)

Standalone — NOT part of run_all.py, which is the fast no-browser gate. Run directly:
    python tests/test_shoes.py            (needs Playwright + WebKit)

Nothing tested this before, on any of the three surfaces, and they had drifted into three
different answers about the same shoe:

    Sko card bar (Planlegging)   accent-blue < 80 %  ·  yellow 80–99  ·  red at 100
    Innsikter warning            warn at 85 %        ·  urgent at 95
    Sko oversikt (dashboard)     ⚠️ at 90 %          ·  🔴 at 100

So a shoe at 88 % showed a yellow bar, an urgent-ish insight and no dashboard mark at all.
This suite pins the merged behaviour:

  1. ONE SET OF THRESHOLDS — 75 % yellow, 90 % red. Asserted on all three surfaces against the
     SAME shoe, because "they agree" is the whole point of the change; testing them separately
     would pass even if they drifted apart again.
  2. RED MEANS THE SAME EVERYWHERE. The insight fires exactly when the bar goes red — not before
     (nagging for months of yellow) and not after (telling you when it is already too late).
  3. NO LIMIT MEANS SILENCE. The insight used to judge a limitless shoe against a hidden 400 km
     that appeared on no screen. All three surfaces must now say nothing at all.

No local data file exists; every session is synthesised in-page.
"""
import pathlib, sys
sys.stdout.reconfigure(encoding='utf-8')   # æøå + ⚠️ 🔴 in the assertions
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


# Four shoes, one per band, plus one with no limit at all. Every limit is 100 km so the
# percentages are readable as-is and a threshold change shows up as an obvious number.
#   Fersk     40/100 =  40 %  green
#   Halvveis  80/100 =  80 %  yellow   (would have been YELLOW under the old bar too, but the
#                                       old insight fired here and the new one must not)
#   Sliten    92/100 =  92 %  red      (old bar was still yellow here — the regression case)
#   Utslitt  110/100 = 110 %  red + spent
#   Ukjent   380 km, NO limit           must be silent on all three surfaces.
#                                       ⚠️ 380 is chosen so the OLD hidden 400 km default
#                                       would put it at 95 % = RED. At 95 km it sat at 24 %
#                                       under that default — green either way — so the
#                                       'stays silent' checks passed without ever
#                                       distinguishing the two builds.
SEED = """() => {
  const run = (id, dato, distanse, sko) => ({
    id, dato, uke: '2026-30', oktnavn: 'Tur', okttype: 'Easy', treningsplan: 'Egentrening',
    løpetype: 'utendors', distanse, varighet: distanse * 360, tempo: 360, soner: [0,0,0,0,0], sko,
  });
  localStorage.setItem('lpl_cache', JSON.stringify({
    sessions: [
      run('a1', '2026-08-01', 20,   'Fersk'),    run('a2', '2026-08-08', 20,   'Fersk'),
      run('b1', '2026-08-01', 40,   'Halvveis'), run('b2', '2026-08-08', 40,   'Halvveis'),
      run('c1', '2026-08-01', 46,   'Sliten'),   run('c2', '2026-08-08', 46,   'Sliten'),
      run('d1', '2026-08-01', 55,   'Utslitt'),  run('d2', '2026-08-08', 55,   'Utslitt'),
      run('e1', '2026-08-01', 190,  'Ukjent'),   run('e2', '2026-08-08', 190,  'Ukjent'),
    ],
    shoes: [
      { name: 'Fersk',    retirementKm: 100 },
      { name: 'Halvveis', retirementKm: 100 },
      { name: 'Sliten',   retirementKm: 100 },
      { name: 'Utslitt',  retirementKm: 100 },
      { name: 'Ukjent' },
    ],
    shoeDefaults: {}, goals: {}, events: [], plannedSessions: [], settings: { zones: [] },
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
    pg.wait_for_timeout(600)

    # ── 1. The shared function, at its boundaries ───────────────────────────────────────────
    print("== one definition, and its edges ==")
    bands = pg.evaluate("""() => {
      const at = (km, limit) => { const w = shoeWear(km, limit ? { retirementKm: limit } : {});
                                  return w ? w.band : 'null'; };   // 380 = 95 % of the old default
      return { p0: at(0,100), p74: at(74.9,100), p75: at(75,100), p89: at(89.9,100),
               p90: at(90,100), p100: at(100,100), p150: at(150,100), noLimit: at(380, null) };
    }""")
    check("0 % is green", bands['p0'], 'green')
    check("74.9 % is still green", bands['p74'], 'green')
    check("75 % turns yellow — the boundary is inclusive", bands['p75'], 'yellow')
    check("89.9 % is still yellow", bands['p89'], 'yellow')
    check("90 % turns red, BEFORE the limit, not at it", bands['p90'], 'red')
    check("100 % is red", bands['p100'], 'red')
    check("past the limit stays red", bands['p150'], 'red')
    check("⚠️ no limit set returns null — nothing to say", bands['noLimit'], 'null')

    spent = pg.evaluate("""() => ({
      at89: shoeWear(89, { retirementKm: 100 }).spent,
      at100: shoeWear(100, { retirementKm: 100 }).spent,
      pctCapped: shoeWear(500, { retirementKm: 100 }).pct,
    })""")
    check("not spent below the limit", spent['at89'], False)
    check("spent at the limit", spent['at100'], True)
    check("the bar never overflows past 100 %", spent['pctCapped'], 100)

    # ── 2. ⚠️ ALL THREE SURFACES, SAME SHOE ─────────────────────────────────────────────────
    # Asserted together rather than one section each: the change is that they AGREE, and three
    # separate sections would still pass if they drifted back apart.
    print("== the bar, the dashboard mark and the insight agree ==")
    pg.evaluate("() => switchTab('plan')")
    pg.wait_for_timeout(400)
    # Anchor on each card's own action button. '#shoeList > div' is the flex WRAPPER holding every
    # card, so querying a bar fill from it returned the first shoe's bar for all five names — a
    # lookup that reported agreement because it never actually distinguished them.
    bars = pg.evaluate("""() => {
      const out = {};
      for (const k of ['Fersk','Halvveis','Sliten','Utslitt','Ukjent']) {
        const btn = document.querySelector(`#shoeList [data-shoe-name="${k}"]`);
        const card = btn && btn.closest('div[style*="border-radius:8px"]');
        if (!card) { out[k] = '<<card not found>>'; continue; }
        const fill = card.querySelector('.shoe-retire-bar-fill');
        out[k] = fill ? fill.style.background : null;
      }
      return out;
    }""")
    check("40 % draws a green bar", bars.get('Fersk'), 'var(--green)')
    check("80 % draws a yellow bar", bars.get('Halvveis'), 'var(--yellow)')
    check("92 % draws a RED bar — the old code was still yellow here",
          bars.get('Sliten'), 'var(--danger)')
    check("110 % draws a red bar", bars.get('Utslitt'), 'var(--danger)')
    check("⚠️ a shoe with no limit draws no bar at all", bars.get('Ukjent'), None)

    pg.evaluate("() => switchTab('dash')")
    pg.wait_for_timeout(500)
    chart = pg.evaluate("() => (document.getElementById('shoeBarChart') || {}).innerText || ''")
    check("the dashboard marks 92 % with ⚠️", '⚠️' in chart.split('Sliten')[1][:40], True)
    check("...and 110 % with 🔴", '🔴' in chart.split('Utslitt')[1][:40], True)
    check("80 % gets no dashboard mark — it is yellow, not red",
          any(c in chart.split('Halvveis')[1][:40] for c in ('⚠️', '🔴')), False)
    check("...and neither does 40 %",
          any(c in chart.split('Fersk')[1][:40] for c in ('⚠️', '🔴')), False)

    ins = pg.evaluate("""() => {
      const el = document.getElementById('insightContent');
      return el ? el.innerText : '<<no insights element>>';
    }""")
    check("the insight fires for the red shoe", 'Sliten' in ins, True)
    check("...and for the spent one", 'Utslitt' in ins, True)
    check("⚠️ it does NOT fire at yellow — that would nag for months", 'Halvveis' in ins, False)
    check("...nor at green", 'Fersk' in ins, False)
    check("⚠️ nor for a shoe with no limit — no hidden 400 km default any more",
          'Ukjent' in ins, False)

    # ── 3. Wording says which state it is ───────────────────────────────────────────────────
    print("== a shoe past its limit reads differently from one approaching it ==")
    check("approaching says so", 'nærmer seg pensjonering' in ins, True)
    check("past the limit says THAT instead", 'over grensen' in ins.lower(), True)

    pg.evaluate("() => switchTab('plan')")
    pg.wait_for_timeout(400)
    plan = pg.locator('#shoeList').inner_text()
    check("the card names the state too", 'Over grensen' in plan, True)
    check("...and still projects a finish date while there is life left",
          'Ferdig om ca.' in plan, True)

    # ── 4. Retired shoes drop out ───────────────────────────────────────────────────────────
    print("== retiring a shoe silences it ==")
    pg.evaluate("() => { Store.updateShoe('Sliten', { retired: true }); Settings.render(); }")
    pg.wait_for_timeout(400)
    after = pg.evaluate("""() => {
      const cards = [...document.querySelectorAll('#shoeList > div')]
        .filter(c => c.textContent.includes('Sliten'));
      return cards.length ? !!cards[0].querySelector('.shoe-retire-bar-fill') : '<<gone>>';
    }""")
    check("a retired shoe shows no wear bar", after, False)
    pg.evaluate("() => switchTab('dash')")
    pg.wait_for_timeout(500)
    ins2 = pg.evaluate("""() => {
      const el = document.getElementById('insightContent');
      return el ? el.innerText : '';
    }""")
    check("...and no longer warns", 'Sliten' in ins2, False)

    # ── 5. 402 px ───────────────────────────────────────────────────────────────────────────
    # ── Standard sko: session group × venue (2026-09-20) ───────────────────────────────────────
    # «Standard sko» knew only Ute/Inne, and Tempo/Intervaller auto-switch to Tredemølle — so every
    # indoor session got the same shoe whether it was an easy run or intervals. Now the GROUP picks
    # first (Rolig = Easy/Steady/Long, Fart = Tempo/Intervaller) and falls back to «Ellers» per venue.
    print("== the shoe rule: group first, venue fallback ==")
    sp = b.new_page(viewport={"width": 1280, "height": 900})
    serr = []
    sp.on("pageerror", lambda e: serr.append(str(e)))
    sp.on("dialog", lambda d: d.accept())
    sp.add_init_script(FREEZE)

    def seed(groups=None, planned=None, retired=()):
        """A fresh store: shoes A/B/C, «Ellers» = A out / B in, plus whatever grid is under test."""
        sp.goto(APP)
        sp.evaluate("""([groups, planned, retired]) => localStorage.setItem('lpl_cache', JSON.stringify({
            sessions: [{ id:'s1', dato:'2026-08-10', uke:'2026-33', oktnavn:'Tur', okttype:'Easy',
                         treningsplan:'Egentrening', løpetype:'utendors', distanse:5, varighet:1800,
                         soner:[0,0,0,0,0], sko:'A' }],
            shoes: ['A','B','C'].map(n => ({ name:n, retired: retired.indexOf(n) >= 0 })),
            shoeDefaults: Object.assign({ outdoor:'A', treadmill:'B' }, groups ? { groups } : {}),
            plannedSessions: planned || [], goals:{}, events:[], settings:{ zones: [] },
            lastUpdated:'' }))""", [groups, planned, list(retired)])
        sp.goto(APP)
        sp.wait_for_timeout(500)
        sp.evaluate("() => switchTab('form')")
        sp.wait_for_timeout(200)

    def pick(okttype, venue=None):
        """Choose a type (and optionally a venue) the way a person would, then read #fSko."""
        sp.select_option("#fOkttype", okttype)
        sp.wait_for_timeout(150)
        if venue:
            sp.select_option("#fLopetype", venue)
            sp.wait_for_timeout(150)
        return sp.input_value("#fSko")

    GROUPS = {"rolig": {"treadmill": "A"}, "fart": {"treadmill": "C"}}
    seed()
    check("control: with no grid, the venue still decides (today's behaviour)",
          [pick("Easy", "treadmill"), pick("Easy", "utendors")], ["B", "A"])
    seed(GROUPS)
    check("Easy indoors takes the Rolig cell, not «Ellers»", pick("Easy", "treadmill"), "A")
    check("Steady counts as Rolig", pick("Steady", "treadmill"), "A")
    check("Intervaller switches venue AND takes the Fart cell", pick("Intervaller"), "C")
    check("...and the venue is Tredemølle, as before", sp.input_value("#fLopetype"), "treadmill")
    check("Fart outdoors has no cell → «Ellers» for Utendørs", pick("Intervaller", "utendors"), "A")
    check("Race is not grouped → «Ellers»", pick("Race", "treadmill"), "B")
    seed(GROUPS, retired=["A"])
    check("a retired shoe in a cell is ignored", pick("Easy", "treadmill"), "B")

    # A hand-picked shoe is final — the rule must not take it back when the type changes afterwards.
    seed(GROUPS)
    pick("Easy", "treadmill")
    sp.select_option("#fSko", "B")
    sp.wait_for_timeout(100)
    check("a hand-picked shoe survives a type change", pick("Intervaller"), "B")
    sp.evaluate("() => Form.clear()")
    sp.wait_for_timeout(250)
    # Økt-type deliberately SURVIVES clear() (logging two of the same type in a row is the common
    # case), so the cleared form is still Intervaller/Tredemølle — the rule's answer there is C, and
    # the point of the check is that it is no longer the hand-picked B.
    check("...and a cleared form obeys the rule again",
          [sp.input_value("#fOkttype"), sp.input_value("#fSko")], ["Intervaller", "C"])

    # ⚠️ The ordering fix: clear() applied the shoe BEFORE the Runna prefill set Økt-type, so a fresh
    # form on an interval day picked the easy shoe. Frozen clock = 2026-08-18.
    seed(GROUPS, planned=[{"id": "p1", "date": "2026-08-18", "okttype": "Intervaller",
                           "distance": 6, "title": "5x1000"}])
    sp.evaluate("() => Form.clear()")
    sp.wait_for_timeout(250)
    check("a planned interval day prefills the Fart shoe",
          [sp.input_value("#fOkttype"), sp.input_value("#fSko")], ["Intervaller", "C"])

    # A planned LONG day is the case the ordering actually protects: applyVenueForType re-applies the
    # shoe for Tempo/Intervaller by itself, so only a type it does NOT move can catch a clear() that
    # picks the shoe before the prefill knows the type. Before the fix this kept the previous form's
    # answer (fart → «Ellers» A) instead of the Rolig cell.
    seed({"rolig": {"outdoor": "C"}, "fart": {"treadmill": "B"}},
         planned=[{"id": "p2", "date": "2026-08-18", "okttype": "Long", "distance": 15, "title": "Langtur"}])
    pick("Intervaller")                      # leaves the form on fart/treadmill = B
    sp.evaluate("() => Form.clear()")
    sp.wait_for_timeout(250)
    check("a planned long day prefills the Rolig shoe, not the previous form's",
          [sp.input_value("#fOkttype"), sp.input_value("#fSko")], ["Long", "C"])

    print("== Standard sko settings write only what is set ==")
    seed()
    sp.evaluate("() => switchTab('plan')")
    sp.wait_for_timeout(300)
    sp.select_option("#defaultShoeFartTreadmill", "C")
    sp.wait_for_timeout(150)
    check("a group cell persists", sp.evaluate("() => Store.data.shoeDefaults.groups"),
          {"fart": {"treadmill": "C"}})
    sp.select_option("#defaultShoeFartTreadmill", "")
    sp.wait_for_timeout(150)
    check("...and blanking it leaves no empty scaffolding",
          sp.evaluate("() => 'groups' in Store.data.shoeDefaults"), False)
    sp.select_option("#defaultShoeOutdoor", "C")
    sp.wait_for_timeout(150)
    check("the «Ellers» row still writes the original per-venue key",
          sp.evaluate("() => Store.data.shoeDefaults.outdoor"), "C")

    # ── The shoe Strava already knows (2026-09-20) ──────────────────────────────────────────────
    # He sets the shoe per run in Strava, so that beats the rule — but a forgotten gear change sends
    # Strava's default, which looks identical to a deliberate one. Hence the visible hint.
    print("== Strava's gear picks the shoe, and says so ==")
    seed(GROUPS)
    sp.evaluate("() => Form.applyStravaGear({ id: 'g-c', name: 'C' })")
    sp.wait_for_timeout(100)
    check("a name match selects that shoe", sp.input_value("#fSko"), "C")
    check("...and says where it came from", sp.text_content("#shoeSrcHint"), "Sko fra Strava: C")
    check("...and stores the link, so the name may change later",
          sp.evaluate("() => Store.data.shoes.find(s => s.name === 'C').stravaGearId"), "g-c")
    sp.evaluate("() => { Store.data.shoes.find(s => s.name === 'C').name = 'C2'; Form.refreshShoeDropdown('A'); }")
    sp.evaluate("() => Form.applyStravaGear({ id: 'g-c', name: 'helt annet navn' })")
    sp.wait_for_timeout(100)
    check("the stored link wins over the name", sp.input_value("#fSko"), "C2")

    seed(GROUPS)
    sp.select_option("#fOkttype", "Easy")
    sp.select_option("#fLopetype", "treadmill")
    sp.wait_for_timeout(150)
    sp.evaluate("() => Form.applyStravaGear({ id: 'g-x', name: 'Ukjent sko' })")
    sp.wait_for_timeout(100)
    check("unknown gear leaves the rule's pick alone", sp.input_value("#fSko"), "A")
    check("...and asks to be connected", "ikke koblet" in (sp.text_content("#shoeSrcHint") or ""), True)
    # His own pick teaches it the link — nothing is inferred from a pattern.
    sp.select_option("#fSko", "B")
    sp.evaluate("""() => { document.getElementById('fDistanse').value = '5';
        document.getElementById('fVarighet').removeAttribute('readonly');
        document.getElementById('fVarighet').value = '0:30:00'; }""")
    sp.click("#btnSaveSession")
    sp.wait_for_timeout(400)
    check("saving links the gear to the shoe he picked",
          sp.evaluate("() => Store.data.shoes.find(s => s.name === 'B').stravaGearId"), "g-x")
    # ⚠️ Move the dropdown OFF B first. Without that, this passed even with the link-storing line
    # disabled — the field was already showing B from the pick above (falsification, 2026-09-20).
    check("...and the next import of that gear resolves by itself",
          sp.evaluate("""() => { Form.shoeTouched = false; Form.refreshShoeDropdown('A');
              Form.applyStravaGear({ id: 'g-x' });
              return document.getElementById('fSko').value; }"""), "B")

    seed(GROUPS)
    sp.select_option("#fOkttype", "Easy")
    sp.select_option("#fLopetype", "treadmill")
    sp.select_option("#fSko", "B")           # a hand-pick in this form
    sp.wait_for_timeout(150)
    sp.evaluate("() => Form.applyStravaGear({ id: 'g-c2', name: 'C' })")
    sp.wait_for_timeout(100)
    check("a hand-picked shoe beats Strava too", sp.input_value("#fSko"), "B")
    seed(GROUPS, retired=["C"])
    sp.evaluate("() => Form.applyStravaGear({ id: 'g-c3', name: 'C' })")
    sp.wait_for_timeout(100)
    check("a retired shoe is never selected from gear", sp.input_value("#fSko") != "C", True)

    # ⚠️ Through the REAL import path, not applyStravaGear directly: the checks above all called the
    # helper, so disabling its one call site in _populate broke nothing (falsification, 2026-09-20).
    # Strava is stubbed — no network, no token.
    print("== the gear arrives through «Hent fra Strava» ==")
    seed(GROUPS)
    STUB = """(gear) => {
      StravaIO.fetchActivityDetail = async () => ({ id: 9001, calories: 400, gear });
      StravaIO.fetchZones = async () => null;
      window.__act = { id: 9001, distance: 8000, moving_time: 2700, trainer: true,
                       has_heartrate: false, average_speed: 2.96, timezone: '(GMT+01:00) Europe/Oslo' };
    }"""
    sp.evaluate(STUB, {"id": "g-pop", "name": "C"})
    sp.evaluate("() => StravaImport._populate(window.__act)")
    sp.wait_for_timeout(500)
    check("the imported activity's shoe is selected", sp.input_value("#fSko"), "C")
    check("...and named as Strava's", sp.text_content("#shoeSrcHint"), "Sko fra Strava: C")
    # Re-pulling while EDITING must not move the shoe — that promise predates this feature.
    sp.evaluate("() => { Form.editId = 's1'; Form.refreshShoeDropdown('B'); }")
    sp.evaluate("() => StravaImport._populate(window.__act)")
    sp.wait_for_timeout(500)
    check("an edit's re-pull leaves the saved shoe alone", sp.input_value("#fSko"), "B")
    sp.evaluate("() => { Form.editId = null; }")

    check("no shoe-rule page errors", serr, [])
    sp.close()

    print("== 402 px ==")
    pg.set_viewport_size({"width": 402, "height": 900})
    pg.evaluate("() => switchTab('plan')")
    pg.wait_for_timeout(500)
    check("nothing overflows the viewport",
          pg.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1"), True)

    check("no page errors", errs, [])
    b.close()

print(f"\n{passed}/{passed + failed} passed" + (f"  ({failed} FAILED)" if failed else ""))
sys.exit(1 if failed else 0)
