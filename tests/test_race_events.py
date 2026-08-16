"""Verify race handling and additive .ics imports.  (2026-08-08)

Standalone — NOT part of run_all.py, which is the fast no-browser gate. Run directly:
    python tests/test_race_events.py       (needs Playwright + WebKit)

Four things, none of which a Python port can reach because they are all form state and DOM:

  1. A race's Treningsplan is DERIVED. A race closing a training block keeps that block's plan;
     a parkrun outside every block drops to Egentrening. One-directional, and never overriding
     a hand-pick.
  2. A race's Øktnavn comes from its 🏁 event — "Berlin Marathon", never "Runna Race".
  3. syncEventFields() is the single source for which event fields are visible. The regression it
     exists for: #evtPlanTargets shipped display:none while #newEvtType shipped "Plan", and
     visibility was only ever set by the change handler, so the form opened self-contradicting and
     re-picking the same option fixed nothing (no change event fires).
  4. THE IMPORT INVARIANT: importing a new block's plan must leave earlier blocks' rows intact.
     That one is the reason this file exists — the old import overwrote plannedSessions wholesale
     and destroyed every finished block's planned-vs-actual record without a word.

THE CLOCK IS PINNED (see FREEZE) — the block windows below are absolute dates, so "which block
covers today" must not drift with the real calendar. See memory reference-test-gate, third failure
mode. No local data file exists; everything is synthesised in-page.
"""
import os, pathlib, sys, tempfile
sys.stdout.reconfigure(encoding='utf-8')   # æøå + 🏁 in the assertions
from playwright.sync_api import sync_playwright

# Relative to this file, not the repo checkout path — CI clones somewhere else entirely.
APP = (pathlib.Path(__file__).resolve().parent.parent / "puls.html").as_uri()
passed = failed = 0

# Wednesday 2026-08-05, midday.
FREEZE = """
(() => {
  const R = Date;
  const fixed = new R(2026, 7, 5, 12, 0, 0).getTime();
  function F(...a) { return a.length ? new R(...a) : new R(fixed); }
  F.prototype = R.prototype; F.now = () => fixed; F.parse = R.parse; F.UTC = R.UTC;
  window.Date = F;
})();
"""

# Two blocks, one finished and one active, plus two races: one closing the active block and one
# well outside it.
SEED = """() => {
  localStorage.setItem('lpl_cache', JSON.stringify({
    sessions: [], shoes: [], goals: {}, settings: { zones: [] },
    events: [
      { id:'old',  type:'plan',  title:'Runna 5K',        date:'2026-06-01', endDate:'2026-07-15' },
      { id:'new',  type:'plan',  title:'Runna 10K',       date:'2026-08-03', endDate:'2026-10-01' },
      { id:'rIn',  type:'race',  title:'10K Oslo',        date:'2026-10-01', distanceKm:10 },
      { id:'rOut', type:'race',  title:'Berlin Marathon', date:'2026-11-15', distanceKm:42.2 }
    ],
    plannedSessions: [
      { id:'o1', date:'2026-06-03', okttype:'Easy',  distance:5,  title:'' },
      { id:'o2', date:'2026-06-10', okttype:'Long',  distance:10, title:'' },
      { id:'o3', date:'2026-07-14', okttype:'Tempo', distance:7,  title:'' }
    ],
    lastUpdated: '' }));
}"""


def check(name, got, want):
    global passed, failed
    if got == want:
        passed += 1
        print(f"  PASS {name}")
    else:
        failed += 1
        print(f"  FAIL {name}\n       got  {got!r}\n       want {want!r}")


def ics(entries):
    """Minimal Runna-shaped calendar. parseRunnaIcs needs the *_PLAN_WORKOUT- UID prefix and a km
    distance in the SUMMARY, or it skips the event as strength/ad-hoc."""
    out = ["BEGIN:VCALENDAR", "VERSION:2.0"]
    for n, (date, summary, token) in enumerate(entries, 1):
        out += ["BEGIN:VEVENT",
                f"UID:UPCOMING_PLAN_WORKOUT-day{n}_plan_week_1_{token}_{n}",
                f"DTSTART;VALUE=DATE:{date.replace('-', '')}",
                f"SUMMARY:{summary}", "END:VEVENT"]
    out.append("END:VCALENDAR")
    return "\r\n".join(out)


def boot(pg, tab):
    pg.add_init_script(FREEZE)
    pg.goto(APP)
    pg.evaluate(SEED)
    pg.goto(APP)
    pg.evaluate(f"() => switchTab('{tab}')")
    pg.wait_for_timeout(400)


with sync_playwright() as b0:
    b = b0.webkit.launch()

    # ── 1. Race sessions: derived plan + event-derived name ─────────────────────────────────
    print("== race Treningsplan + Øktnavn ==")
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    perr = []
    pg.on("pageerror", lambda e: perr.append(str(e)))
    boot(pg, 'form')

    def set_date(d):
        pg.evaluate("d => { const e = document.getElementById('fDato'); e.value = d; "
                    "e.dispatchEvent(new Event('change')); }", d)

    plan = lambda: pg.locator('#fTreningsplan').input_value()
    navn = lambda: pg.locator('#fOktnavn').input_value()

    # a race closing the active block -> that block's plan is kept
    set_date('2026-10-01')
    pg.select_option('#fOkttype', 'Race')
    check("race inside a block keeps Runna", plan(), 'Runna')
    check("name comes from the event", navn(), '10K Oslo')
    check("Øktbeskrivelse stays visible", pg.locator('#beskrevelseGroup').is_visible(), True)

    # a race outside every block -> nobody prescribed it
    set_date('2026-11-15')
    check("race outside every block -> Egentrening", plan(), 'Egentrening')
    check("name still from the event", navn(), 'Berlin Marathon')
    check("Øktbeskrivelse hidden for Egentrening", pg.locator('#beskrevelseGroup').is_visible(), False)

    # back to a normal type -> the default is restored, not stranded on Egentrening
    pg.select_option('#fOkttype', 'Easy')
    check("reverting restores the default plan", plan(), 'Runna')
    check("normal auto-name resumes", navn(), 'Runna Easy')

    # a race with no event registered: never "Runna Race", and no stale name left behind
    set_date('2026-11-20')
    pg.select_option('#fOkttype', 'Race')
    check("race with no event -> Egentrening", plan(), 'Egentrening')
    check("never names a race after the programme", navn() == 'Runna Race', False)
    check("stale 'Runna Easy' is cleared", navn(), '')

    # even inside a block, a race is never named by the programme
    set_date('2026-09-15')
    check("race inside a block, no event -> no name invented", navn(), '')
    check("...and the block's plan is still kept", plan(), 'Runna')

    # a hand-picked plan is final
    pg.select_option('#fTreningsplan', 'Runna')
    set_date('2026-11-15')
    check("hand-picked plan survives the derivation", plan(), 'Runna')
    check("...while the name still derives", navn(), 'Berlin Marathon')

    # a typed name is never clobbered
    pg.fill('#fOktnavn', 'Mitt eget navn')
    set_date('2026-10-01')
    check("typed name is never overwritten", navn(), 'Mitt eget navn')

    check("no page errors", perr, [])
    pg.close()

    # ── 2. Event form field visibility ──────────────────────────────────────────────────────
    print("== syncEventFields ==")
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    eerr = []
    pg.on("pageerror", lambda e: eerr.append(str(e)))
    boot(pg, 'plan')
    vis = lambda sel: pg.locator(sel).is_visible()

    # THE REGRESSION: no interaction at all, straight off a fresh load
    check("fresh load: type is Plan", pg.locator('#newEvtType').input_value(), 'plan')
    check("fresh load: plan targets already visible", vis('#evtPlanTargets'), True)
    check("fresh load: race fields hidden", vis('#evtRaceFields'), False)
    check("fresh load: Sluttdato visible", vis('#evtEndDateWrap'), True)

    pg.select_option('#newEvtType', 'race')
    check("race: distance shown", vis('#evtRaceFields'), True)
    check("race: plan targets hidden", vis('#evtPlanTargets'), False)
    check("race: Sluttdato hidden (a race is one day)", vis('#evtEndDateWrap'), False)

    pg.select_option('#newEvtType', 'illness')
    check("illness: neither group shown", (vis('#evtPlanTargets'), vis('#evtRaceFields')), (False, False))
    check("illness: Sluttdato back (it is a period)", vis('#evtEndDateWrap'), True)

    # Distanse takes the slot Sluttdato vacates, so a race is a ONE-LINE row like every other type —
    # it must not push itself onto a second line at desktop width.
    rows = """(t) => {
      document.getElementById('newEvtType').value = t;
      Settings.syncEventFields();
      const tops = ['newEvtDate','evtEndDateWrap','evtRaceFields','newEvtType','newEvtTitle','btnAddEvent']
        .map(i => document.getElementById(i))
        .filter(e => e && e.offsetParent !== null)
        .map(e => Math.round(e.getBoundingClientRect().top));
      return new Set(tops).size;
    }"""
    for t in ('plan', 'race', 'illness'):
        check(f"{t}: event row stays on one line", pg.evaluate(rows, t), 1)

    # a value typed under one type must not reach addEvent under another
    pg.select_option('#newEvtType', 'race')
    pg.fill('#newEvtRaceDist', '21.1')
    pg.select_option('#newEvtType', 'illness')
    pg.fill('#newEvtDate', '2026-12-01')
    pg.fill('#newEvtTitle', 'Forkjølelse')
    pg.click('#btnAddEvent')
    pg.wait_for_timeout(200)
    check("hidden distance never reaches the event",
          pg.evaluate("() => Store.data.events.find(e => e.title === 'Forkjølelse').distanceKm"), None)
    # ...and saving reconciles the form again (the _clearEventForm path)
    check("after save: type back to Plan", pg.locator('#newEvtType').input_value(), 'plan')
    check("after save: plan targets visible again", vis('#evtPlanTargets'), True)

    # distanceKm round-trips through edit
    pg.select_option('#newEvtType', 'race')
    pg.fill('#newEvtDate', '2026-12-06')
    pg.fill('#newEvtTitle', 'Julelopet')
    pg.fill('#newEvtRaceDist', '10')
    pg.click('#btnAddEvent')
    pg.wait_for_timeout(200)
    evid = pg.evaluate("() => Store.data.events.find(e => e.title === 'Julelopet').id")
    check("distance stored", pg.evaluate("id => Store.data.events.find(e => e.id === id).distanceKm", evid), 10)
    pg.evaluate("id => Settings.editEvent(id)", evid)
    pg.wait_for_timeout(200)
    check("edit repopulates the distance", pg.locator('#newEvtRaceDist').input_value(), '10')
    check("edit shows the race group", vis('#evtRaceFields'), True)
    check("edit hides Sluttdato", vis('#evtEndDateWrap'), False)
    # clearing it removes the field rather than leaving a superseded value behind
    pg.fill('#newEvtRaceDist', '')
    pg.click('#btnAddEvent')
    pg.wait_for_timeout(200)
    check("cleared distance is really gone",
          pg.evaluate("id => Store.data.events.find(e => e.id === id).distanceKm", evid), None)

    # an upcoming race with a distance says so; the countdown insight names it too
    check("upcoming race shows its distance",
          '10 km' in pg.locator('#raceHistoryList').inner_text(), True)

    # ── The distance in the Hendelser row ────────────────────────────────────────────────────
    # A race is one day, so it has no end date and that half of the row sits empty; the distance
    # goes there. "Runna 5K test" carries it in the name, "adidas x Anton Sport: Social Run" does
    # not — and it is NOT decorative: distanceKm decides which nearby run gets matched to the race
    # (renderRaceHistory's picker), so a blank one is now visibly blank.
    pg.evaluate("""() => {
      Store.data.events = [
        { id:'f',  type:'vacation', title:'Japan', date:'2026-11-24', endDate:'2026-12-10' },
        { id:'r1', type:'race', title:'Runna 5K test', date:'2026-09-11', distanceKm:5 },
        { id:'r2', type:'race', title:'Social Run',    date:'2026-08-13', distanceKm:10 },
        { id:'r3', type:'race', title:'Halvmaraton',   date:'2026-07-01', distanceKm:21.1 },
        { id:'r4', type:'race', title:'Ukjent',        date:'2026-06-01' }
      ];
      Settings.renderEventList();
    }""")
    pg.wait_for_timeout(200)
    rowtext = lambda i: " ".join(pg.locator('#eventList .event-row').nth(i).inner_text().split())
    check("whole km drops the decimal", "5 km" in rowtext(1), True)
    check("two-digit distance", "10 km" in rowtext(2), True)
    check("fractional distance keeps one place", "21.1 km" in rowtext(3), True)
    check("a race with no distance shows none", "km" in rowtext(4), False)
    # Non-race types keep their end date and must not grow a distance.
    check("vacation row unchanged", "km" in rowtext(0), False)
    check("...and still shows its range", "24.11.2026 – 10.12.2026" in rowtext(0), True)

    check("no page errors", eerr, [])
    pg.close()

    # ── 3. THE IMPORT INVARIANT ─────────────────────────────────────────────────────────────
    print("== additive .ics import ==")
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    ierr = []
    pg.on("pageerror", lambda e: ierr.append(str(e)))
    boot(pg, 'plan')

    stored = lambda: pg.evaluate("() => Store.data.plannedSessions.map(p => p.date)")
    OLD = ['2026-06-03', '2026-06-10', '2026-07-14']
    check("seeded with the finished block's plan", stored(), OLD)
    check("card scopes to the active block (no rows yet)", pg.locator('#plannedList > div').count(), 0)
    check("...and says so rather than 'ingen plan importert'",
          'tidligere blokker' in pg.locator('#plannedList').inner_text(), True)

    tmp = os.path.join(tempfile.gettempdir(), 'puls_test_runna.ics')
    pathlib.Path(tmp).write_text(ics([('2026-08-05', '5 km Easy Run',  'EASY_RUN'),
                                      ('2026-08-07', '12 km Long Run', 'LONG_RUN'),
                                      ('2026-08-10', '8 km Tempo Run', 'TEMPO')]), encoding='utf-8')
    pg.set_input_files('#runnaIcsFile', tmp)
    pg.wait_for_timeout(700)

    check("the earlier block's rows SURVIVE the import",
          stored(), OLD + ['2026-08-05', '2026-08-07', '2026-08-10'])
    check("the finished block still resolves its plan",
          pg.evaluate("() => plannedForBlock('2026-06-01','2026-07-15').map(p => p.date)"), OLD)
    check("the message says what was kept",
          'beholdt' in pg.locator('#plannedImportMsg').inner_text(), True)
    check("card shows only the active block", pg.locator('#plannedList > div').count(), 3)

    # re-importing the SAME block replaces it rather than duplicating
    pathlib.Path(tmp).write_text(ics([('2026-08-05', '6 km Easy Run', 'EASY_RUN'),
                                      ('2026-08-12', '9 km Tempo Run', 'TEMPO')]), encoding='utf-8')
    pg.set_input_files('#runnaIcsFile', tmp)
    pg.wait_for_timeout(700)
    check("re-import replaces its own block cleanly",
          stored(), OLD + ['2026-08-05', '2026-08-12'])
    check("...and still leaves the earlier block alone",
          pg.evaluate("() => plannedForBlock('2026-06-01','2026-07-15').length"), 3)

    check("no page errors", ierr, [])
    pg.close()

    # ── 3b. Importing a plan for a block that is NOT the active one ─────────────────────────
    # Setting the next block up before the current one ends is normal. Anchoring the replaced range
    # on the ACTIVE block's start (rather than on what the import covers) wiped the current block
    # here — the same data loss the additive change exists to prevent, one step narrower.
    print("== importing the NEXT block while the current one is active ==")
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    nerr = []
    pg.on("pageerror", lambda e: nerr.append(str(e)))
    pg.add_init_script(FREEZE)
    pg.goto(APP)
    pg.evaluate("""() => {
      localStorage.setItem('lpl_cache', JSON.stringify({
        sessions: [], shoes: [], goals: {}, settings: { zones: [] },
        events: [
          { id:'cur',  type:'plan', title:'Runna 5K',  date:'2026-07-01', endDate:'2026-08-20' },
          { id:'next', type:'plan', title:'Runna 10K', date:'2026-08-24', endDate:'2026-10-20' }
        ],
        plannedSessions: [
          { id:'c1', date:'2026-07-03', okttype:'Easy',  distance:5, title:'' },
          { id:'c2', date:'2026-07-20', okttype:'Long',  distance:9, title:'' },
          { id:'c3', date:'2026-08-18', okttype:'Tempo', distance:7, title:'' }
        ], lastUpdated: '' }));
    }""")
    pg.goto(APP)
    pg.evaluate("() => switchTab('plan')")
    pg.wait_for_timeout(400)
    CUR = ['2026-07-03', '2026-07-20', '2026-08-18']
    check("the current block is the active one",
          pg.evaluate("() => (activePlanEvent(localISODate())||{}).title"), 'Runna 5K')

    tmp2 = os.path.join(tempfile.gettempdir(), 'puls_test_next.ics')
    pathlib.Path(tmp2).write_text(ics([('2026-08-24', '5 km Easy Run',  'EASY_RUN'),
                                       ('2026-08-26', '10 km Long Run', 'LONG_RUN')]), encoding='utf-8')
    pg.set_input_files('#runnaIcsFile', tmp2)
    pg.wait_for_timeout(700)

    check("the ACTIVE block's plan survives an import that never touched its dates",
          pg.evaluate("() => plannedForBlock('2026-07-01','2026-08-20').map(p => p.date)"), CUR)
    check("the next block's rows landed",
          pg.evaluate("() => plannedForBlock('2026-08-24','2026-10-20').map(p => p.date)"),
          ['2026-08-24', '2026-08-26'])
    check("stored set stays sorted by date",
          pg.evaluate("() => { const d = Store.data.plannedSessions.map(p => p.date); "
                      "return d.join() === d.slice().sort().join(); }"), True)
    check("no page errors", nerr, [])
    os.remove(tmp2)
    os.remove(tmp)
    pg.close()

    # ── 4. Mobile 402px — the new race-fields row ───────────────────────────────────────────
    print("== mobile 402px ==")
    pg = b.new_page(viewport={"width": 402, "height": 900})
    merr = []
    pg.on("pageerror", lambda e: merr.append(str(e)))
    boot(pg, 'plan')
    pg.select_option('#newEvtType', 'race')
    over = pg.evaluate("""() => {
      const row = document.getElementById('evtRaceFields');
      const bad = [];
      // every leaf, not just the row — textContent lies through an ellipsis
      row.querySelectorAll('input,span,div').forEach(el => {
        if (el.scrollWidth > el.clientWidth + 1 && el.clientWidth > 0) bad.push(el.id || el.tagName);
      });
      return { bad, right: row.getBoundingClientRect().right, docW: document.documentElement.clientWidth };
    }""")
    check("no clipped child in the race row", over["bad"], [])
    check("race row within viewport", over["right"] <= over["docW"] + 1, True)
    check("no mobile page errors", merr, [])
    pg.close()

    # ── matchPlannedSessions gating ────────────────────────────────────────────────────────────
    # Reported from real use 2026-08-12: "I dag: Long · 5 km ✓" on a day with no run. An ad-hoc
    # Intervaller run logged the DAY BEFORE had matched the planned Long — it scored 110 (100 type
    # penalty + 10 for a day early), which is terrible, but `if (best)` has no ceiling and it was the
    # only eligible run in the week.
    #
    # WHY THE TIMING MADE IT WORSE, and why a plain "does it match" test would have missed it: the
    # false 'done' exists ONLY while the session is still pending. Run the session and the real one
    # scores ~0, wins, and the symptom vanishes. So the card lied exactly when it was supposed to be
    # telling him what was left. Every case below is dated inside one Mon–Sun week (10.–16.08.2026).
    print("\n== planned-session matching: what may complete a session ==")
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    perr = []
    pg.on("pageerror", lambda e: perr.append(str(e)))
    pg.add_init_script(FREEZE)
    pg.goto(APP)
    pg.wait_for_timeout(400)

    WED = '2026-08-12'

    def matched(actual, planned_type='Long', planned_date=WED):
        """True if `actual` completes a planned session. Calls the function directly — this is
        matching logic, and routing it through the UI would test the renderer instead."""
        pl = [{'id': 'p1', 'date': planned_date, 'okttype': planned_type, 'distance': 5, 'title': ''}]
        a = {'id': 'a1', 'distanse': 5, 'varighet': 1800, 'treningsplan': 'Runna'}
        a.update(actual)
        return pg.evaluate("""([ses, pl]) => {
          Store.data.sessions = ses;
          return Object.keys(matchPlannedSessions(pl)).length > 0;
        }""", [[a], pl])

    # THE BUG: wrong type, one day early.
    check("Tue intervals do NOT complete Wed's Long",
          matched({'dato': '2026-08-11', 'okttype': 'Intervaller', 'distanse': 5.01}), False)
    # ...and the grace it must not break: the same session, genuinely run a day early.
    check("Tue Long DOES complete Wed's Long",
          matched({'dato': '2026-08-11', 'okttype': 'Long'}), True)
    # Swapping intensity on the day is a completed session, not a miss — score is also exactly 100,
    # which is why a score ceiling cannot separate these two cases and the direction rule can.
    check("Wed Tempo completes Wed's Long (swapped on the day)",
          matched({'dato': WED, 'okttype': 'Tempo'}), True)
    check("Thu Tempo completes Wed's Long (ran it late)",
          matched({'dato': '2026-08-13', 'okttype': 'Tempo'}), True)
    check("two days early is still out of range",
          matched({'dato': '2026-08-10', 'okttype': 'Long'}), False)

    # Egentrening means "not part of a programme", so it cannot complete the programme's session —
    # even when type, date and distance all line up perfectly.
    check("Egentrening cannot complete a planned session",
          matched({'dato': WED, 'okttype': 'Long', 'treningsplan': 'Egentrening'}), False)
    check("...the same run as Runna does", matched({'dato': WED, 'okttype': 'Long'}), True)
    # A custom plan is still a programme — the filter excludes Egentrening by name rather than
    # requiring 'Runna', so adding a plan in Innstillinger can't silently break adherence.
    check("a custom plan still completes it",
          matched({'dato': WED, 'okttype': 'Long', 'treningsplan': 'Egen plan X'}), True)

    # ── which planned session gets the credit ──────────────────────────────────────────────────
    # Reported 2026-08-15. The gates above decide WHETHER a run may complete a session; this is the
    # separate question of WHICH one gets it when several compete, and it was wrong.
    #
    # Planned sessions used to be walked in DATE order, each claiming the best still-free run before
    # any later session got a look. Miss one session mid-week and everything after it shifts: with a
    # Mon/Wed/Fri plan and Monday skipped, Easy claimed Wednesday's intervals (score 100),
    # Intervaller claimed Friday's long, and Long — the session actually run — reported as missed.
    #
    # ⚠️ THE COUNT WAS RIGHT THE WHOLE TIME, which is why nothing looked broken: 2 of 3 either way.
    # Only the attribution was wrong, and attribution is exactly what the card uses to say what you
    # still owe. A test asserting "how many matched" would have passed throughout — assert WHICH.
    print("\n== which planned session gets the credit ==")
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    aerr = []
    pg.on("pageerror", lambda e: aerr.append(str(e)))
    pg.add_init_script(FREEZE)
    pg.goto(APP)
    pg.wait_for_timeout(400)

    # One Mon/Wed/Fri week: 10.08 Easy · 12.08 Intervaller · 14.08 Long.
    PLAN = [{'id': 'e', 'date': '2026-08-10', 'okttype': 'Easy', 'distance': 5, 'title': ''},
            {'id': 'i', 'date': '2026-08-12', 'okttype': 'Intervaller', 'distance': 6, 'title': ''},
            {'id': 'l', 'date': '2026-08-14', 'okttype': 'Long', 'distance': 12, 'title': ''}]

    def credits(runs):
        """{plannedId: 'Type@DD' or 'MISS'} — names WHICH run each planned session claimed."""
        ses = [{'id': f'a{n}', 'dato': d, 'okttype': t, 'distanse': km, 'varighet': 1800,
                'treningsplan': 'Runna'} for n, (d, t, km) in enumerate(runs)]
        return pg.evaluate("""([ses, pl]) => {
          Store.data.sessions = ses;
          const m = matchPlannedSessions(pl);
          const by = {}; ses.forEach(s => by[s.id] = s.okttype + '@' + s.dato.slice(8));
          const out = {}; pl.forEach(p => out[p.id] = m[p.id] ? by[m[p.id]] : 'MISS');
          return out;
        }""", [ses, PLAN])

    check("full week: each session gets its own run",
          credits([('2026-08-10', 'Easy', 5), ('2026-08-12', 'Intervaller', 6), ('2026-08-14', 'Long', 12)]),
          {'e': 'Easy@10', 'i': 'Intervaller@12', 'l': 'Long@14'})
    # THE BUG: Monday skipped. Easy used to claim Wednesday's intervals and cascade from there.
    check("missed Monday does not shift the rest of the week",
          credits([('2026-08-12', 'Intervaller', 6), ('2026-08-14', 'Long', 12)]),
          {'e': 'MISS', 'i': 'Intervaller@12', 'l': 'Long@14'})
    check("skipped mid-week session is the one reported missing",
          credits([('2026-08-10', 'Easy', 5), ('2026-08-14', 'Long', 12)]),
          {'e': 'Easy@10', 'i': 'MISS', 'l': 'Long@14'})
    check("one run all week goes to the session it actually was",
          credits([('2026-08-14', 'Long', 12)]),
          {'e': 'MISS', 'i': 'MISS', 'l': 'Long@14'})
    # Displacement must still work — this is the common case and was never broken.
    check("Friday's long run on Saturday still completes it",
          credits([('2026-08-10', 'Easy', 5), ('2026-08-12', 'Intervaller', 6), ('2026-08-15', 'Long', 12)]),
          {'e': 'Easy@10', 'i': 'Intervaller@12', 'l': 'Long@15'})
    # A genuine substitution still counts: nothing else that week, wrong type, on the planned day.
    check("substituted session on the planned day still counts",
          credits([('2026-08-12', 'Tempo', 6)]),
          {'e': 'MISS', 'i': 'Tempo@12', 'l': 'MISS'})

    check("no attribution page errors", aerr, [])
    pg.close()

    check("no page errors", perr, [])
    pg.close()

    b.close()

print(f"\n{passed}/{passed+failed} passed" + ("" if not failed else f"  ({failed} FAILED)"))
sys.exit(1 if failed else 0)
