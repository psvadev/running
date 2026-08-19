"""Verify the per-distance goal times — the 🎯 Mål section and the field that feeds it.  (2026-08-18)

Standalone — NOT part of run_all.py, which is the fast no-browser gate. Run directly:
    python tests/test_goals.py            (needs Playwright + WebKit)

A goal time is the only number on the Rekorder card that Puls does not measure, which is exactly
what makes it worth testing:

  1. THE VENUE PICK. The goal is deliberately venue-agnostic, but the PR and prognose printed beside
     it are measurements, so each keeps its 🏃/⚙️ icon. Picking the faster of the two is a bare
     comparison that would invert in total silence — DATA.md "Belt vs GPS" is the whole reason the
     rest of this card never merges the two populations, so a row that quietly showed an indoor time
     labelled 🏃 would be a lie in the one place nothing else checks.
  2. THE JOIN KEYS. computeDistancePRs rows carry `key`; computePerfCurve rows carry only `label`.
     The section matches on a different field for each, and a wrong one yields no context at all —
     which looks exactly like "not run yet" and would never be noticed by eye.
  3. THE PICKER FLOOR. Goals start at 1 km, mirroring computePerfCurve's own `km >= 1`. Two
     hand-kept copies of one rule is enumeration rot waiting to happen, so the lists are compared
     against each other rather than against a number written down here.
  4. REJECTION IS VISIBLE AND NON-DESTRUCTIVE. A refused entry must keep what he typed — cleared and
     never-filled look identical on screen.

No local data file exists; every session is synthesised in-page.
"""
import pathlib, sys
sys.stdout.reconfigure(encoding='utf-8')   # æøå + 🎯 🏃 ⚙️ in the assertions
from playwright.sync_api import sync_playwright

# Relative to this file, not the repo checkout path — CI clones somewhere else entirely.
APP = (pathlib.Path(__file__).resolve().parent.parent / "puls.html").as_uri()
passed = failed = 0

# Tuesday 2026-08-18, midday. Pinned because the Årsmål card below is year-scoped and every seeded
# date is absolute — an unpinned clock makes this suite start failing on 1 January for reasons that
# have nothing to do with goals. See memory reference-test-gate, third failure mode.
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


# Five distances, one per venue combination, so the icon in each row has a different reason to be
# what it is. Goals are listed newest-distance-FIRST on purpose — the render must sort them.
#   1 km  Ute only            5 km  both, Ute faster (26:01 vs 28:20)
#   10 km Inne only           15 km both, Inne faster (1:26:40 vs 1:30:00)
#   HM    neither → prognose alone
MATRIX = """() => {
  const belt = (dato, distanse, varighet) => ({
    id: dato, dato, uke: '2026-27', oktnavn: 'Belte', okttype: 'Easy', treningsplan: 'Egentrening',
    løpetype: 'treadmill', distanse, varighet, tempo: varighet / distanse, soner: [0,0,0,0,0],
  });
  localStorage.setItem('lpl_cache', JSON.stringify({
    sessions: [belt('2026-07-01', 10, 3700), belt('2026-07-02', 5, 1700), belt('2026-07-03', 15, 5200)],
    shoes: [], goals: {}, events: [], plannedSessions: [], settings: { zones: [] },
    bestEffortsTop3: {
      '1k':  [{ t: 272,  d: '2026-06-14' }],
      '5k':  [{ t: 1561, d: '2026-06-14' }],
      '15k': [{ t: 5400, d: '2026-06-20' }],
    },
    distanceGoals: { half: 7200, '15k': 5000, '10k': 3000, '5k': 1500, '1k': 240 },
    lastUpdated: '' }));
}"""

# Goals set before there is anything to compare them against — the only way a row can legitimately
# carry no context at all, since one anchor is enough to give EVERY distance a prognose however far
# away it is. One outdoor Easy run: no bestEffortsTop3 so no Ute PR, not a belt run so no Inne PR,
# and nothing maximal to anchor a projection. It cannot be zero sessions — renderDashboard swaps the
# whole tab for its empty state before it reaches any card.
BARE = """() => {
  localStorage.setItem('lpl_cache', JSON.stringify({
    sessions: [{ id:'a', dato:'2026-07-04', uke:'2026-27', oktnavn:'Tur', okttype:'Easy',
                 treningsplan:'Egentrening', løpetype:'utendors', distanse:4, varighet:1500,
                 tempo:375, soner:[0,0,0,0,0] }],
    shoes: [], goals: {}, events: [], plannedSessions: [], settings: { zones: [] },
    distanceGoals: { '5k': 1500 }, lastUpdated: '' }));
}"""

# No distance goals, but an Årsmål and a run — so "the section is hidden" means the section, and not
# renderDashboard's whole-tab empty state standing in front of it. Also the starting point for the
# Planlegging route below.
EMPTY = """() => {
  localStorage.setItem('lpl_cache', JSON.stringify({
    sessions: [{ id:'a', dato:'2026-07-04', uke:'2026-27', oktnavn:'Tur', okttype:'Easy',
                 treningsplan:'Egentrening', løpetype:'utendors', distanse:4, varighet:1500,
                 tempo:375, soner:[0,0,0,0,0] }],
    shoes: [], goals: { '2026': 900 }, events: [], plannedSessions: [],
    settings: { zones: [] }, lastUpdated: '' }));
}"""

ROWS = """() => [...document.querySelectorAll('#goalTimeList .top3-row')].map(r => {
  const s = r.querySelectorAll('span');
  return { label: s[0].textContent.trim(), goal: s[1].textContent.trim(), ctx: s[2].textContent.trim() };
})"""


def boot(pg, seed, tab):
    pg.add_init_script(FREEZE)
    pg.goto(APP)
    pg.evaluate(seed)
    pg.goto(APP)
    pg.evaluate(f"() => switchTab('{tab}')")
    pg.wait_for_timeout(400)


with sync_playwright() as pw:
    b = pw.webkit.launch()

    # ── 1. The venue pick, the join, and the ordering ───────────────────────────────────────
    print("== 🎯 Mål rows: which venue, and where the numbers come from ==")
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    boot(pg, MATRIX, 'dash')

    check("section is shown", pg.locator('#goalTimeSection').is_visible(), True)
    rows = pg.evaluate(ROWS)

    # Ascending distance, NOT the order the keys sit in the stored object.
    check("rows are sorted by distance, not entry order",
          [r['label'] for r in rows], ['1 km', '5 km', '10 km', '15 km', 'Halvmaraton'])
    # secsToHms, matching the two sections directly above it in the same card.
    check("goal is the stored time", [r['goal'] for r in rows],
          ['🎯 0:04:00', '🎯 0:25:00', '🎯 0:50:00', '🎯 1:23:20', '🎯 2:00:00'])

    by = {r['label']: r for r in rows}
    # THE VENUE PICK — four rows, four different reasons for the icon.
    check("Ute only  → 🏃 and the outdoor time",
          by['1 km']['ctx'].startswith('PR 🏃 0:04:32'), True)
    check("Inne only → ⚙️ and the belt time",
          by['10 km']['ctx'].startswith('PR ⚙️ 1:01:40'), True)
    check("both, Ute faster  → 🏃 0:26:01 (not the 0:28:20 belt run)",
          by['5 km']['ctx'].startswith('PR 🏃 0:26:01'), True)
    check("both, Inne faster → ⚙️ 1:26:40 (not the 1:30:00 segment)",
          by['15 km']['ctx'].startswith('PR ⚙️ 1:26:40'), True)
    check("no PR at all → the PR clause is omitted entirely",
          'PR' in by['Halvmaraton']['ctx'], False)

    # THE JOIN — prognose rows carry `label` where PR rows carry `key`, so a wrong match field on
    # either side yields a silently empty clause rather than an error.
    check("...but the prognose clause is there", by['Halvmaraton']['ctx'].startswith('prognose '), True)
    check("prognose names a venue too",
          any(i in by['Halvmaraton']['ctx'] for i in ('🏃', '⚙️')), True)
    # Cross-check one prognose figure against the card that already renders it, rather than against a
    # number copied into this file: same distance, same value, or the join picked the wrong row.
    prog_hm = pg.evaluate("""() => {
      const r = computePerfCurve(Store.data.sessions, computeDistancePRs(Store.data.sessions))
                  .find(x => x.label === 'Halvmaraton');
      const e = r.ute && (!r.inne || r.ute.t <= r.inne.t) ? r.ute : r.inne;
      return secsToHms(e.t);
    }""")
    check("prognose figure equals what computePerfCurve says", prog_hm in by['Halvmaraton']['ctx'], True)

    # A dash in the tables above states a fact about his running. Here it would only repeat them.
    check("nothing is dashed in this section",
          '–' in pg.locator('#goalTimeList').inner_text(), False)

    # ── 2. No data yet: a goal still renders, with nothing beside it ────────────────────────
    print("== a goal set before there is anything to compare it to ==")
    boot(pg, BARE, 'dash')
    rows = pg.evaluate(ROWS)
    check("the row is there", [r['label'] for r in rows], ['5 km'])
    check("...with its goal", rows[0]['goal'], '🎯 0:25:00')
    check("...and an empty context cell, not a dash", rows[0]['ctx'], '')
    check("Distanse-PR itself has nothing to show", pg.locator('#distPRList').inner_text().startswith('Ingen'), True)
    check("...and there is no prognose either", pg.locator('#prognoseSection').is_visible(), False)

    # ── 3. The empty state ─────────────────────────────────────────────────────────────────
    print("== no goals at all ==")
    boot(pg, EMPTY, 'dash')
    check("section is hidden", pg.locator('#goalTimeSection').is_visible(), False)
    check("Årsmål is unaffected", pg.locator('#goalCard').is_visible(), True)

    # ── 4. THE ROUTE: Planlegging → store → dashboard ───────────────────────────────────────
    # Setting a goal by writing to the store proves the render. It does not prove a single thing
    # about the form that is the only way he will ever actually set one.
    print("== the Planlegging route ==")
    pg.on("dialog", lambda d: d.accept())
    boot(pg, EMPTY, 'plan')

    # The floor is not a number written down here — it is computePerfCurve's, compared to itself.
    opts = pg.eval_on_selector_all('#newDistGoalKey option', "o => o.map(x => x.value)")
    check("picker offers exactly the distances a prognose can reach",
          opts, pg.evaluate("() => BEST_EFFORT_DISTS.filter(d => d.km >= 1).map(d => d.key)"))
    check("...so 400 m is not among them", '400m' in opts, False)
    check("empty list says so", pg.locator('#distGoalList').inner_text().startswith('Ingen'), True)

    def add(key, text):
        pg.select_option('#newDistGoalKey', key)
        pg.fill('#newDistGoalTime', text)
        pg.click('#btnAddDistGoal')
        pg.wait_for_timeout(120)

    goals = lambda: pg.evaluate("() => Store.data.distanceGoals || {}")

    add('5k', '25:00')
    check("mm:ss is stored as seconds", goals(), {'5k': 1500})
    check("...and rendered back in the list", '25:00' in pg.locator('#distGoalList').inner_text(), True)
    check("the input is cleared on success", pg.locator('#newDistGoalTime').input_value(), '')

    add('half', '2:00:00')
    check("h:mm:ss round-trips too", goals(), {'5k': 1500, 'half': 7200})
    check("...and reads back as it was typed",
          '2:00:00' in pg.locator('#distGoalList').inner_text(), True)

    # Årsmål shares the card. It must not share any state with it.
    check("Årsmål is untouched", pg.evaluate("() => Store.data.goals"), {'2026': 900})

    # ── 5. Rejection: visible, and it never eats the input ──────────────────────────────────
    print("== a refused entry keeps what he typed ==")
    before = goals()
    add('10k', '59:75')
    check("seconds must be seconds", goals(), before)
    check("...the reason is on screen", pg.locator('#distGoalMsg').inner_text().startswith('Skriv tiden'), True)
    check("...and the field still holds it", pg.locator('#newDistGoalTime').input_value(), '59:75')

    add('10k', 'i morgen')
    check("gibberish is refused", goals(), before)
    check("...without clearing it", pg.locator('#newDistGoalTime').input_value(), 'i morgen')

    # The unit slip this guard exists for: "25:00" is a perfectly valid time and complete nonsense
    # on a marathon. Threshold read from the page, never copied here.
    floor = pg.evaluate("() => GOAL_MIN_PACE_SECS")
    add('marathon', '25:00')
    check("a marathon goal at 5k pace is refused", goals(), before)
    check("...and says why", 'verdensrekorden' in pg.locator('#distGoalMsg').inner_text(), True)
    check("...at the floor the page defines", floor, 120)
    add('marathon', '4:00:00')   # 5:41/km — slow enough to be real, fast enough to be a goal
    check("a plausible marathon goal is accepted", 'marathon' in goals(), True)

    # ── 6. Edit and delete ─────────────────────────────────────────────────────────────────
    print("== edit in place, and delete ==")
    pg.click('[data-edit-dgoal="5k"]')
    pg.wait_for_timeout(80)
    check("the time is prefilled", pg.locator('#newDistGoalTime').input_value(), '25:00')
    check("the distance is locked while editing", pg.locator('#newDistGoalKey').is_disabled(), True)
    check("the button says Oppdater", pg.locator('#btnAddDistGoal').inner_text(), 'Oppdater')
    pg.fill('#newDistGoalTime', '24:30')
    pg.click('#btnAddDistGoal')
    pg.wait_for_timeout(120)
    check("editing updates in place, adding nothing", goals()['5k'], 1470)
    check("...and unlocks the picker again", pg.locator('#newDistGoalKey').is_disabled(), False)
    check("...and restores the button", pg.locator('#btnAddDistGoal').inner_text(), '+ Legg til')

    pg.click('[data-edit-dgoal="half"]')
    pg.click('#btnCancelDistGoalEdit')
    pg.wait_for_timeout(80)
    check("Avbryt unlocks the picker", pg.locator('#newDistGoalKey').is_disabled(), False)
    check("...and empties the field", pg.locator('#newDistGoalTime').input_value(), '')

    pg.click('[data-del-dgoal="half"]')
    pg.wait_for_timeout(120)
    check("delete removes exactly one", sorted(goals()), ['5k', 'marathon'])

    # The dashboard is the surface all of that exists to feed — check it followed along.
    pg.evaluate("() => switchTab('dash')")
    pg.wait_for_timeout(300)
    check("dashboard reflects the edits",
          [r['label'] for r in pg.evaluate(ROWS)], ['5 km', 'Maraton'])
    check("...with the edited time", pg.evaluate(ROWS)[0]['goal'], '🎯 0:24:30')

    # ── 7. Mobile ──────────────────────────────────────────────────────────────────────────
    print("== 402 px ==")
    pg.set_viewport_size({"width": 402, "height": 900})
    pg.wait_for_timeout(200)
    over = pg.evaluate("""() => {
      const el = document.getElementById('goalTimeSection');
      return { wide: el.scrollWidth > document.documentElement.clientWidth,
               stacked: getComputedStyle(document.querySelector('#goalTimeList .top3-row')).flexDirection };
    }""")
    check("nothing overflows the viewport", over['wide'], False)
    check("rows stack like their neighbours", over['stacked'], 'column')

    check("no page errors", errs, [])
    b.close()

print(f"\n{passed}/{passed+failed} passed" + ("" if not failed else f"  ({failed} FAILED)"))
sys.exit(1 if failed else 0)
