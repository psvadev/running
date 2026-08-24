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
