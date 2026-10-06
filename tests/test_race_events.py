"""Verify race handling and additive .ics imports.  (2026-08-08)

Standalone — NOT part of run_all.py, which is the fast no-browser gate. Run directly:
    python tests/test_race_events.py       (needs Playwright + WebKit)
    PW_ENGINE=firefox python tests/test_race_events.py  (also chromium; firefox is his main browser)

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
ENGINE = os.environ.get("PW_ENGINE", "webkit")
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
    b = getattr(b0, ENGINE).launch()
    print(f"engine: {ENGINE}")

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

    # Egentrening names nothing after a programme, so switching to it takes a generated «Runna
    # Intervaller» back — by the race's rule above: a stale generated name is worse than none (found
    # 2026-09-29: a run could be saved as Egentrening named «Runna …»). Switching back restores it,
    # and a typed name stays through both.
    pg.evaluate("() => Form.clear()")
    set_date('2026-08-12')
    pg.select_option('#fOkttype', 'Intervaller')
    check("control: the form generated «Runna Intervaller»", navn(), 'Runna Intervaller')
    pg.select_option('#fTreningsplan', 'Egentrening')
    check("switching to Egentrening takes the generated name back", navn(), '')
    pg.select_option('#fTreningsplan', 'Runna')
    check("...and switching back restores it", navn(), 'Runna Intervaller')
    pg.fill('#fOktnavn', 'Bakkeintervaller')
    pg.select_option('#fTreningsplan', 'Egentrening')
    check("a typed name stays when the plan becomes Egentrening", navn(), 'Bakkeintervaller')

    check("no page errors", perr, [])
    pg.close()

    # ── 1b. The plan prefills Øktbeskrivelse ────────────────────────────────────────────────
    # Runna does not reliably push the prescription to Strava, so it never reached Puls and the
    # field sat empty for most easy and interval sessions — which is why the export's
    # [Øktbeskrivelse] was usually blank. The .ics has it for every planned session, so the plan is
    # the reliable source. Fill-when-empty, the same guard the Strava populate uses.
    print("== plan prefills Øktbeskrivelse ==")
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    berr = []
    pg.on("pageerror", lambda e: berr.append(str(e)))
    pg.add_init_script(FREEZE)
    pg.goto(APP)
    pg.evaluate("""() => {
      localStorage.setItem('lpl_cache', JSON.stringify({
        sessions: [], shoes: [], goals: {}, settings: { zones: [] },
        events: [{ id:'b', type:'plan', title:'Runna 5K', date:'2026-08-03', endDate:'2026-10-01' }],
        plannedSessions: [
          { id:'p1', date:'2026-08-06', okttype:'Intervaller', distance:5, title:'400m Repeats',
            beskrivelse:'1.5km warm up\\n5 reps of:\\n400m at 5:40/km' },
          { id:'p2', date:'2026-08-08', okttype:'Easy', distance:6, title:'',
            beskrivelse:'6km easy at a conversational pace' },
          { id:'p3', date:'2026-08-10', okttype:'Long', distance:9, title:'' }
        ], lastUpdated: '' }));
    }""")
    pg.goto(APP)
    pg.evaluate("() => switchTab('form')")
    pg.wait_for_timeout(400)
    setd = lambda d: pg.evaluate("d => { const e = document.getElementById('fDato'); e.value = d; "
                                 "e.dispatchEvent(new Event('change')); }", d)
    besk = lambda: pg.locator('#fBeskrivelse').input_value()

    setd('2026-08-06')
    check("the plan's prescription lands in Øktbeskrivelse", '400m at 5:40/km' in besk(), True)
    check("...and the type still prefills too", pg.locator('#fOkttype').input_value(), 'Intervaller')

    # A typed value is never clobbered — the same rule Mål distanse follows.
    pg.fill('#fBeskrivelse', 'Min egen beskrivelse')
    setd('2026-08-08')
    check("a typed description survives a date change", besk(), 'Min egen beskrivelse')

    # Cleared, it fills again from whatever day you land on.
    pg.fill('#fBeskrivelse', '')
    setd('2026-08-08')
    check("cleared, it fills from the new day", besk(), '6km easy at a conversational pace')

    # A planned session without one leaves the field alone rather than blanking it.
    pg.fill('#fBeskrivelse', '')
    setd('2026-08-10')
    check("a planned day with no prescription fills nothing", besk(), '')
    check("...but still prefills what it does have", pg.locator('#fOkttype').input_value(), 'Long')
    check("no page errors", berr, [])
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

    # ── 2b. WHERE THE DISTANCE LIVES ────────────────────────────────────────────────────────
    # A run carries a km distance and strength does not — but an UPCOMING session puts it in the
    # SUMMARY while a COMPLETED session with a NAMED workout ("400m Repeats") has none there and
    # carries it in the description. Reading only the SUMMARY dropped every completed named interval
    # session: 10 across a real 17-week block, making a 33-session plan look like 23.
    print("== parseRunnaIcs: distance in SUMMARY or in DESCRIPTION ==")
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    boot(pg, 'plan')
    MIXED = "\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0",
        # upcoming run — distance in the SUMMARY, as before
        "BEGIN:VEVENT", "UID:UPCOMING_PLAN_WORKOUT-d1_plan_week_1_EASY_RUN_0",
        "DTSTART;VALUE=DATE:20260810", "SUMMARY:\U0001F3C3 7.5km Easy Run • 7.5km",
        "DESCRIPTION:Easy Run • 7.5km • 50m - 55m\\n\\n7.5km easy at a conversational pace"
        "\\n\\n\U0001F4F2 View in the Runna app: https://club.runna.com/x", "END:VEVENT",
        # completed NAMED workout — nothing in the SUMMARY, distance in the description
        "BEGIN:VEVENT", "UID:COMPLETED_PLAN_WORKOUT-abc123",
        "DTSTART;VALUE=DATE:20260812", "SUMMARY:\U0001F3C3 400m Repeats",
        "DESCRIPTION:\U0001F4CA Summary:\\nDistance: 4.27km\\nTime: 34:36\\nAvg Pace: 8:05 /km"
        "\\n\\n\U0001F4CB Description:\\n1.5km warm up then 8 x 400m repeats", "END:VEVENT",
        # strength — no distance ANYWHERE, so the fallback must not let it in
        "BEGIN:VEVENT", "UID:UPCOMING_PLAN_WORKOUT-d3_plan_week_1_LEGS_AND_CORE_0",
        "DTSTART;VALUE=DATE:20260813", "SUMMARY:\U0001F3CB️ Legs & Core Strength • 25m - 35m",
        "DESCRIPTION:Legs & Core Strength • 25m - 35m", "END:VEVENT",
        # ad-hoc non-plan run — excluded by UID regardless of where its distance sits
        "BEGIN:VEVENT", "UID:COMPLETED_NON_PLAN_WORKOUT-xyz",
        "DTSTART:20260814T170000Z", "SUMMARY:\U0001F3C3 Evening Run",
        "DESCRIPTION:\U0001F4CA Summary:\\nDistance: 6.10km", "END:VEVENT",
        "END:VCALENDAR"])
    got = pg.evaluate("(t) => parseRunnaIcs(t).map(p => [p.date, p.okttype, p.distance])", MIXED)
    desc = pg.evaluate("(t) => Object.fromEntries(parseRunnaIcs(t).map(p => [p.date, p.beskrivelse]))", MIXED)
    check("upcoming run kept (distance in SUMMARY)", ['2026-08-10', 'Easy', 7.5] in got, True)
    check("completed NAMED workout kept (distance in DESCRIPTION)",
          ['2026-08-12', 'Intervaller', 4.27] in got, True)
    check("strength still excluded — no distance anywhere", len(got), 2)
    check("...and the ad-hoc non-plan run too, despite having one",
          any(d == '2026-08-14' for d, _, _ in got), False)

    # ── Two faults found in a REAL import, 2026-09-11 ────────────────────────────────────────
    #
    # 1. THE SESSION TOTAL IS AFTER THE BULLET. "1km Repeats • 9km" is a 9 km session of 1 km reps;
    #    reading the first km in the summary stored it as 1 km. It hid for months because Runna
    #    normally repeats the total in the name ("8km Easy Run • 8km"), where both numbers agree —
    #    only a workout NAMED after its rep distance can expose it.
    # 2. TAPER_INTERVALS MATCHED NOTHING, so it fell through to the fuzzy pass, where a bare
    #    \brace\b read «Race Pace Practice K's» as a RACE. That would pre-fill the log form with
    #    Økt-type Race and let a 7.5 km practice session anchor Formkurve and Prognose.
    #
    # ⚠️ The controls are the point: the ordinary shapes must be untouched, and a REAL race must
    # still be a Race. A fix that simply stopped trusting \brace\b would pass every check above.
    print("== parseRunnaIcs: rep distance in the name, and race-PACE is not a race ==")
    TRAPS = "\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0",
        # the rep distance differs from the total — the case that broke
        "BEGIN:VEVENT", "UID:UPCOMING_PLAN_WORKOUT-d1_plan_week_1_INTERVALS_0",
        "DTSTART;VALUE=DATE:20261027", "SUMMARY:\U0001F3C3 1km Repeats • 9km",
        "DESCRIPTION:Intervals • 9km • 55m - 1h10m\\n\\n2km warm up", "END:VEVENT",
        # an unknown FAMILY (TAPER_INTERVALS) whose summary also says "Race Pace"
        "BEGIN:VEVENT", "UID:UPCOMING_PLAN_WORKOUT-d2_plan_week_9_TAPER_INTERVALS_0",
        "DTSTART;VALUE=DATE:20261116", "SUMMARY:\U0001F3C3 Race Pace Practice K's • 7.5km",
        "DESCRIPTION:Taper Intervals • 7.5km • 45m - 55m\\n\\n2km warm up", "END:VEVENT",
        # an unknown family whose words give the fuzzy pass NOTHING to match — only the tail answers
        "BEGIN:VEVENT", "UID:UPCOMING_PLAN_WORKOUT-d6_plan_week_9_TAPER_TEMPO_0",
        "DTSTART;VALUE=DATE:20261117", "SUMMARY:\U0001F3C3 Practice K's • 6km",
        "DESCRIPTION:Taper Session • 6km\\n\\n2km warm up", "END:VEVENT",
        # CONTROL: a real race must survive as one
        "BEGIN:VEVENT", "UID:UPCOMING_PLAN_WORKOUT-d3_plan_week_9_RACE_0",
        "DTSTART;VALUE=DATE:20261119", "SUMMARY:\U0001F3C3 10km Race • 10km",
        "DESCRIPTION:Race • 10km\\n\\ngive it everything", "END:VEVENT",
        # CONTROL: the ordinary shape, where name and total agree
        "BEGIN:VEVENT", "UID:UPCOMING_PLAN_WORKOUT-d4_plan_week_1_EASY_RUN_0",
        "DTSTART;VALUE=DATE:20261028", "SUMMARY:\U0001F3C3 8km Easy Run • 8km",
        "DESCRIPTION:Easy Run • 8km", "END:VEVENT",
        # CONTROL: no bullet at all — the whole summary is still read
        "BEGIN:VEVENT", "UID:UPCOMING_PLAN_WORKOUT-d5_plan_week_1_LONG_RUN_0",
        "DTSTART;VALUE=DATE:20261029", "SUMMARY:\U0001F3C3 12km Long Run",
        "DESCRIPTION:Long Run • 12km", "END:VEVENT",
        "END:VCALENDAR"])
    trap = pg.evaluate("(t) => Object.fromEntries(parseRunnaIcs(t).map(p => [p.date, [p.okttype, p.distance]]))", TRAPS)
    check("the total after the bullet wins over the rep distance", trap['2026-10-27'], ['Intervaller', 9])
    check("an unknown *_INTERVALS family resolves by its tail", trap['2026-11-16'][0], 'Intervaller')
    check("...and takes its own distance", trap['2026-11-16'][1], 7.5)
    # ⚠️ VACUOUS-CHECK #18, caught by falsification: the line above passes with OR without the family
    # lookup, because its description says "Taper Intervals" and the fuzzy pass matches \binterval
    # on that. It pins the OUTCOME for the real event and nothing about the MECHANISM. This one
    # discriminates — a family tail the fuzzy pass has no word to find, so only the tail lookup
    # can answer it. Without the fix it comes out Easy.
    check("...and a family the fuzzy pass cannot guess", trap['2026-11-17'], ['Tempo', 6])
    check("a REAL race is still a Race", trap['2026-11-19'], ['Race', 10])
    check("the ordinary shape is untouched", trap['2026-10-28'], ['Easy', 8])
    check("a summary with no bullet still parses", trap['2026-10-29'], ['Long', 12])

    # ⚠️ The token fix above means TAPER_INTERVALS never REACHES the fuzzy pass, so it does not pin
    # the \brace\b rule at all. These two do: a token no family can claim, so the fuzzy pass runs.
    # "race pace" is how half of Runna's quality sessions describe their target, so a bare \brace\b
    # turns every one of them into a Race — while a genuine race must still come out as one.
    FUZZ = "\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0",
        "BEGIN:VEVENT", "UID:UPCOMING_PLAN_WORKOUT-d1_plan_week_1_MYSTERY_THING_0",
        "DTSTART;VALUE=DATE:20261201", "SUMMARY:\U0001F3C3 Race Pace Practice • 6km",
        "DESCRIPTION:Mystery Session • 6km\\n\\n4 x 1km at race pace", "END:VEVENT",
        "BEGIN:VEVENT", "UID:UPCOMING_PLAN_WORKOUT-d2_plan_week_1_MYSTERY_THING_1",
        "DTSTART;VALUE=DATE:20261202", "SUMMARY:\U0001F3C3 10km Race • 10km",
        "DESCRIPTION:Mystery Session • 10km\\n\\nrace day", "END:VEVENT",
        "END:VCALENDAR"])
    fz = pg.evaluate("(t) => Object.fromEntries(parseRunnaIcs(t).map(p => [p.date, p.okttype]))", FUZZ)
    check("fuzzy pass: 'race pace' is not a race", fz['2026-12-01'] == 'Race', False)
    check("fuzzy pass: a real race still is one", fz['2026-12-02'], 'Race')

    # ── THE PRESCRIPTION, kept for the log form's prefill ────────────────────────────────────
    # An UPCOMING event's description IS the prescription. A COMPLETED one leads with the actuals
    # (Distance / Time / Avg Pace) and the prescription follows "Description:". Storing the actuals
    # in Oktbeskrivelse would be wrong twice: that field means what was PRESCRIBED, and distance and
    # pace are already columns on the session.
    check("upcoming: the description is the prescription",
          desc['2026-08-10'].startswith('Easy Run'), True)
    check("...keeping the body", 'conversational pace' in desc['2026-08-10'], True)
    check("...but dropping the Runna app link line", 'club.runna.com' in desc['2026-08-10'], False)
    check("completed: prescription taken from after 'Description:'",
          desc['2026-08-12'], '1.5km warm up then 8 x 400m repeats')
    check("...NOT the actuals that precede it", 'Distance: 4.27km' in desc['2026-08-12'], False)

    # ── WHAT THE IMPORT MAY AND MAY NOT KEEP ────────────────────────────────────────────────
    # ⚠️ PRIVACY, asserted rather than trusted. A Runna .ics carries GEO coordinates and a LOCATION on
    # every completed session, X-USER-TIMEZONE on all of them, and a club.runna.com link holding a
    # personal share token plus the day/activity UUID. NONE of it may reach storage. `sourceUrl` used
    # to — stored on every planned session and read by nothing, so the single most identifying string
    # in the file was persisted for no purpose. Removed 2026-08-27.
    LOCATED = "\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0",
        "BEGIN:VEVENT", "UID:COMPLETED_PLAN_WORKOUT-secret-uuid-1234",
        "DTSTART;VALUE=DATE:20260812", "SUMMARY:\U0001F3C3 400m Repeats",
        "DESCRIPTION:\U0001F4CA Summary:\\nDistance: 4.27km\\n\\n\U0001F4CB Description:\\n1.5km warm up"
        "\\n\\n\U0001F4F2 View in the Runna app: https://club.runna.com/n9Tx/activities?activityId=secret-uuid-1234",
        "LOCATION:Skøyen, Oslo, Norway",
        "GEO:59.91616325015404;10.634521393154518",
        "X-USER-TIMEZONE:Europe/Oslo", "END:VEVENT", "END:VCALENDAR"])
    blob = pg.evaluate("(t) => JSON.stringify(parseRunnaIcs(t))", LOCATED)
    for needle, what in [("59.916", "GEO latitude"), ("10.634", "GEO longitude"),
                         ("Skøyen", "LOCATION"), ("Europe/Oslo", "timezone"),
                         ("club.runna.com", "the Runna link"), ("n9Tx", "the personal share token")]:
        check(f"{what} never reaches the parsed session", needle in blob, False)
    check("no sourceUrl field at all",
          pg.evaluate("(t) => 'sourceUrl' in parseRunnaIcs(t)[0]", LOCATED), False)
    # The opaque activity id IS kept — it is the dedup key, and re-import correctness depends on it.
    check("...but the id is still there, since dedup needs it",
          pg.evaluate("(t) => parseRunnaIcs(t)[0].id", LOCATED), "secret-uuid-1234")

    # Runna's own estimate for the session. UPCOMING only — a completed event carries none.
    EST = "\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0",
        "BEGIN:VEVENT", "UID:UPCOMING_PLAN_WORKOUT-d9_plan_week_2_INTERVALS_0",
        "DTSTART;VALUE=DATE:20260901", "SUMMARY:\U0001F3C3 Pyramid Intervals • 6km",
        "DESCRIPTION:Intervals • 6km • 45m - 50m\\n\\n1km warm up at a conversational pace",
        "X-WORKOUT-ESTIMATED-DURATION:3000", "END:VEVENT", "END:VCALENDAR"])
    check("X-WORKOUT-ESTIMATED-DURATION is read", pg.evaluate("(t) => parseRunnaIcs(t)[0].estimatedSecs", EST), 3000)
    check("...and is null when absent", pg.evaluate("(t) => parseRunnaIcs(t)[0].estimatedSecs", LOCATED), None)
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
    # The active block has no imported plan yet, so the card falls back to the most recent block that
    # HAS one — never to a merged bucket of every block ever imported, which is what it used to do and
    # what stops being readable after a few plans.
    check("falls back to the most recent block with a plan", pg.locator('#plannedList > div').count(), 3)
    check("...and names which block that is", 'Siste blokk · Runna 5K' in pg.locator('#plannedAdherence').inner_text(), True)
    check("...with no index, since it is the only block with a plan",
          'ANDRE BLOKKER' in pg.locator('#plannedList').inner_text().upper(), False)

    tmp = os.path.join(tempfile.gettempdir(), 'puls_test_runna.ics')
    pathlib.Path(tmp).write_text(ics([('2026-08-05', '5 km Easy Run',  'EASY_RUN'),
                                      ('2026-08-07', '12 km Long Run', 'LONG_RUN'),
                                      ('2026-08-10', '8 km Tempo Run', 'TEMPO')]), encoding='utf-8')
    pg.set_input_files('#runnaIcsFile', tmp)
    pg.wait_for_timeout(700)

    # ── THE PREVIEW WRITES NOTHING ──────────────────────────────────────────────────────────
    # Picking the file used to import on the spot. It is the only destructive control on this card
    # that never asked, and it made "what is in this file?" answerable only by performing the write.
    check("picking a file only previews", stored(), OLD)
    check("...naming the count and the span", 'klare til import' in pg.locator('#plannedImportMsg').inner_text(), True)
    check("...and what it would replace", 'beholdes' in pg.locator('#plannedImportMsg').inner_text()
          or 'erstattes' in pg.locator('#plannedImportMsg').inner_text(), True)
    # Skipped rows carry a DATE RANGE, not just a count: a count cannot distinguish a complete older
    # plan from a pruned remnant of one, and importing a remnant would measure that block's adherence
    # against half its real plan. Needs a file that actually HAS pre-block entries — the one above has
    # none, so asserting the span against it would have passed or failed for the wrong reason.
    # Skipped now means "inside no registered block at all" — a session in a FINISHED block is
    # imported, which is the point of the scope change. These two predate every Plan event.
    tmp_pre = os.path.join(tempfile.gettempdir(), 'puls_test_runna_pre.ics')
    pathlib.Path(tmp_pre).write_text(ics([('2026-05-01', '5 km Easy Run', 'EASY_RUN'),
                                          ('2026-05-10', '8 km Long Run', 'LONG_RUN'),
                                          ('2026-08-05', '5 km Easy Run', 'EASY_RUN')]), encoding='utf-8')
    pg.set_input_files('#runnaIcsFile', tmp_pre)
    pg.wait_for_timeout(700)
    ptxt = pg.locator('#plannedImportMsg').inner_text()
    check("rows inside no block are skipped", '2 økter utenfor alle blokker' in ptxt, True)
    check("...and carry a date span, not just a count", '(01.05.2026 – 10.05.2026)' in ptxt, True)
    # Cancelling must leave the store exactly as it was, not half-applied.
    pg.click('#btnCancelIcs')
    pg.wait_for_timeout(200)
    check("cancel writes nothing", stored(), OLD)
    os.remove(tmp_pre)
    check("...and clears the preview", pg.locator('#plannedImportMsg').inner_text().strip(), '')

    pg.set_input_files('#runnaIcsFile', tmp)
    pg.wait_for_timeout(700)
    pg.click('#btnConfirmIcs')
    pg.wait_for_timeout(500)

    check("the earlier block's rows SURVIVE the import",
          stored(), OLD + ['2026-08-05', '2026-08-07', '2026-08-10'])
    check("the finished block still resolves its plan",
          pg.evaluate("() => plannedForBlock('2026-06-01','2026-07-15').map(p => p.date)"), OLD)
    check("the message says what was kept",
          'beholdt' in pg.locator('#plannedImportMsg').inner_text(), True)
    # THE SCOPING RULE: the session list is ONE block's, and every other block collapses to a single
    # index row. Flat in the number of blocks, not sessions — five finished plans is five rows.
    check("session rows are the active block's only", pg.locator('.planned-block-row').count()
          and pg.locator('#plannedList > div').count() - 1, 3)
    check("the earlier block becomes ONE index row", pg.locator('.planned-block-row').count(), 1)
    check("...naming it", 'Runna 5K' in pg.locator('.planned-block-row').inner_text(), True)
    check("...with its OWN adherence, not the active block's",
          '0 av 3' in pg.locator('.planned-block-row').inner_text(), True)
    # The headline counts THIS block (3), never the 6 now in the store. Before the scoping change it
    # widened to every block ever imported the moment no block was active, under the same label.
    check("...and the adherence line counts this block only",
          '3 økter i planen' in pg.locator('#plannedAdherence').inner_text(), True)
    # It opens the drill-down that already exists rather than a second inline copy of it.
    pg.locator('.planned-block-row').click()
    pg.wait_for_timeout(400)
    check("clicking it opens that block's drill-down",
          'Runna 5K' in pg.locator('#detailTitle').inner_text(), True)
    pg.evaluate("() => DetailPanel.close()")
    pg.wait_for_timeout(200)

    # re-importing the SAME block replaces it rather than duplicating
    pathlib.Path(tmp).write_text(ics([('2026-08-05', '6 km Easy Run', 'EASY_RUN'),
                                      ('2026-08-12', '9 km Tempo Run', 'TEMPO')]), encoding='utf-8')
    pg.set_input_files('#runnaIcsFile', tmp)
    pg.wait_for_timeout(700)
    pg.click('#btnConfirmIcs')
    pg.wait_for_timeout(500)
    # A re-import replaces the dates it CARRIES and keeps the ones it no longer mentions. Runna drops
    # a skipped day from the feed once a block moves on, so clearing the whole span would erase
    # exactly the misses — quietly turning a real record into a perfect one.
    check("re-import replaces the dates it carries",
          stored(), OLD + ['2026-08-05', '2026-08-07', '2026-08-10', '2026-08-12'])
    check("...keeping rows whose dates it no longer carries",
          '2026-08-07' in stored() and '2026-08-10' in stored(), True)
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
    pg.click('#btnConfirmIcs')
    pg.wait_for_timeout(500)

    check("the ACTIVE block's plan survives an import that never touched its dates",
          pg.evaluate("() => plannedForBlock('2026-07-01','2026-08-20').map(p => p.date)"), CUR)
    check("the next block's rows landed",
          pg.evaluate("() => plannedForBlock('2026-08-24','2026-10-20').map(p => p.date)"),
          ['2026-08-24', '2026-08-26'])
    check("stored set stays sorted by date",
          pg.evaluate("() => { const d = Store.data.plannedSessions.map(p => p.date); "
                      "return d.join() === d.slice().sort().join(); }"), True)
    check("no page errors", nerr, [])
    pg.close()

    # ── 3c. ⚠️ THE ASSERTION THAT WAS MISSING BOTH TIMES THIS FUNCTION LOST DATA ─────────────
    # Ranges are per BLOCK, never one span across blocks. An import covering two blocks with a third
    # sitting between them would, under a single [first, last], delete that middle block outright —
    # a block the import never mentioned. Bug one replaced everything; bug two replaced from the
    # wrong anchor; both survived tests that only asserted the party named in the bug report.
    print("== a block the import does NOT cover is not written at all ==")
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    merr = []
    pg.on("pageerror", lambda e: merr.append(str(e)))
    pg.add_init_script(FREEZE)
    pg.goto(APP)
    pg.evaluate("""() => {
      localStorage.setItem('lpl_cache', JSON.stringify({
        sessions: [], shoes: [], goals: {}, settings: { zones: [] },
        events: [
          { id:'A', type:'plan', title:'Blokk A', date:'2026-05-01', endDate:'2026-05-31' },
          { id:'B', type:'plan', title:'Blokk B', date:'2026-06-01', endDate:'2026-06-30' },
          { id:'C', type:'plan', title:'Blokk C', date:'2026-07-01', endDate:'2026-07-31' }
        ],
        plannedSessions: [
          { id:'a1', date:'2026-05-05', okttype:'Easy',  distance:5,  title:'' },
          { id:'b1', date:'2026-06-05', okttype:'Long',  distance:9,  title:'' },
          { id:'b2', date:'2026-06-20', okttype:'Tempo', distance:7,  title:'' },
          { id:'c1', date:'2026-07-05', okttype:'Easy',  distance:6,  title:'' }
        ], lastUpdated: '' }));
    }""")
    pg.goto(APP)
    pg.evaluate("() => switchTab('plan')")
    pg.wait_for_timeout(400)
    MID = pg.evaluate("() => Store.data.plannedSessions.filter(p => p.date >= '2026-06-01' "
                      "&& p.date <= '2026-06-30').map(p => JSON.stringify(p))")

    # Each block gets rows BRACKETING its stored one, so the span actually covers it and replacement
    # is what is being tested. A single-row import would span one day and leave the stored row in
    # place — correct, but it would test nothing about replacing.
    tmp3 = os.path.join(tempfile.gettempdir(), 'puls_test_gap.ics')
    pathlib.Path(tmp3).write_text(ics([('2026-05-03', '6 km Easy Run',  'EASY_RUN'),   # block A
                                       ('2026-05-20', '7 km Long Run',  'LONG_RUN'),   # block A
                                       ('2026-07-02', '5 km Easy Run',  'EASY_RUN'),   # block C
                                       ('2026-07-09', '8 km Long Run',  'LONG_RUN')]), # block C
                                  encoding='utf-8')
    pg.set_input_files('#runnaIcsFile', tmp3)
    pg.wait_for_timeout(700)
    ptxt = pg.locator('#plannedImportMsg').inner_text()
    check("preview names one line per block it touches", ptxt.count('erstattes'), 2)
    check("...naming block A", 'Blokk A' in ptxt, True)
    check("...and block C", 'Blokk C' in ptxt, True)
    check("...and NOT the untouched block B", 'Blokk B' in ptxt, False)
    pg.click('#btnConfirmIcs')
    pg.wait_for_timeout(500)

    check("⚠️ the untouched middle block is byte-identical",
          pg.evaluate("() => Store.data.plannedSessions.filter(p => p.date >= '2026-06-01' "
                      "&& p.date <= '2026-06-30').map(p => JSON.stringify(p))"), MID)
    check("block A takes the imported dates, its own untouched date surviving",
          pg.evaluate("() => plannedForBlock('2026-05-01','2026-05-31').map(p => p.date)"),
          ['2026-05-03', '2026-05-05', '2026-05-20'])
    check("block C likewise", pg.evaluate("() => plannedForBlock('2026-07-01','2026-07-31').map(p => p.date)"),
          ['2026-07-02', '2026-07-05', '2026-07-09'])
    check("nothing was invented or lost overall",
          pg.evaluate("() => Store.data.plannedSessions.length"), 8)
    check("stored set stays sorted", pg.evaluate(
        "() => { const d = Store.data.plannedSessions.map(p => p.date); "
        "return d.join() === d.slice().sort().join(); }"), True)
    check("no page errors", merr, [])
    pg.close()

    # A row inside a touched block but OUTSIDE the imported span survives — a mid-block re-import
    # whose .ics no longer carries the completed days must not delete that block's history. Same
    # rule the single-block path has always had; it needs re-checking now that spans are per block.
    print("== a partial import does not delete the rest of its own block ==")
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    pg.add_init_script(FREEZE)
    pg.goto(APP)
    pg.evaluate("""() => {
      localStorage.setItem('lpl_cache', JSON.stringify({
        sessions: [], shoes: [], goals: {}, settings: { zones: [] },
        events: [{ id:'A', type:'plan', title:'Blokk A', date:'2026-05-01', endDate:'2026-05-31' }],
        plannedSessions: [
          { id:'early', date:'2026-05-02', okttype:'Easy', distance:5, title:'' },
          { id:'mid',   date:'2026-05-15', okttype:'Long', distance:9, title:'' }
        ], lastUpdated: '' }));
    }""")
    pg.goto(APP)
    pg.evaluate("() => switchTab('plan')")
    pg.wait_for_timeout(400)
    tmp4 = os.path.join(tempfile.gettempdir(), 'puls_test_partial.ics')
    pathlib.Path(tmp4).write_text(ics([('2026-05-20', '6 km Easy Run', 'EASY_RUN'),
                                       ('2026-05-27', '7 km Long Run', 'LONG_RUN')]), encoding='utf-8')
    pg.set_input_files('#runnaIcsFile', tmp4)
    pg.wait_for_timeout(700)
    pg.click('#btnConfirmIcs')
    pg.wait_for_timeout(500)
    check("earlier rows in the same block survive a later-only import",
          pg.evaluate("() => Store.data.plannedSessions.map(p => p.date)"),
          ['2026-05-02', '2026-05-15', '2026-05-20', '2026-05-27'])
    os.remove(tmp4)
    os.remove(tmp3)
    os.remove(tmp2)
    os.remove(tmp)
    pg.close()

    # ── 3d. ⚠️ THE MISS MUST SURVIVE A RE-IMPORT ─────────────────────────────────────────────
    # Runna's feed keeps only the days you COMPLETED once a block moves on; a skipped session leaves
    # no event behind. So a re-import that clears its whole span deletes exactly the misses, and a
    # block that was 2-of-3 silently becomes 2-of-2 · 100%. Found live: a retro-imported 17-week
    # block scored 33 av 33 because every event in the feed was a completion.
    print("== a skipped session is not erased by a later re-import ==")
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    serr = []
    pg.on("pageerror", lambda e: serr.append(str(e)))
    pg.add_init_script(FREEZE)
    pg.goto(APP)
    pg.evaluate("""() => {
      localStorage.setItem('lpl_cache', JSON.stringify({
        sessions: [], shoes: [], goals: {}, settings: { zones: [] },
        events: [{ id:'b', type:'plan', title:'Blokk', date:'2026-07-01', endDate:'2026-08-20' }],
        plannedSessions: [
          { id:'s1', date:'2026-07-06', okttype:'Easy',  distance:5, title:'' },
          { id:'s2', date:'2026-07-08', okttype:'Long',  distance:9, title:'' },
          { id:'s3', date:'2026-07-10', okttype:'Tempo', distance:7, title:'' }
        ], lastUpdated: '' }));
    }""")
    pg.goto(APP)
    pg.evaluate("() => switchTab('plan')")
    pg.wait_for_timeout(400)
    # The re-import carries only the two he DID: the middle one was skipped and has left the feed.
    tmp5 = os.path.join(tempfile.gettempdir(), 'puls_test_miss.ics')
    pathlib.Path(tmp5).write_text(ics([('2026-07-06', '5 km Easy Run',  'EASY_RUN'),
                                       ('2026-07-10', '7 km Tempo Run', 'TEMPO')]), encoding='utf-8')
    pg.set_input_files('#runnaIcsFile', tmp5)
    pg.wait_for_timeout(700)
    pg.click('#btnConfirmIcs')
    pg.wait_for_timeout(500)
    check("⚠️ the skipped session's row survives",
          pg.evaluate("() => Store.data.plannedSessions.map(p => p.date)"),
          ['2026-07-06', '2026-07-08', '2026-07-10'])
    check("...so the block still knows it was 3 sessions, not 2",
          pg.evaluate("() => plannedForBlock('2026-07-01','2026-08-20').length"), 3)
    check("no page errors", serr, [])
    os.remove(tmp5)
    pg.close()

    # ── 3e. ⚠️ A PLAN REBUILT FROM COMPLETIONS CANNOT REPORT ADHERENCE ───────────────────────
    # A finished block's feed holds only the days you DID, so matching it against your runs returns
    # 100% by construction — the misses were never in the denominator. The ticks are true; the ratio
    # is not. Found live: a retro-imported 17-week block with a 21-day hole in it scored 33 av 33.
    print("== completion-derived rows report a count, never a percentage ==")
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    cerr = []
    pg.on("pageerror", lambda e: cerr.append(str(e)))
    pg.add_init_script(FREEZE)
    pg.goto(APP)
    pg.evaluate("""() => {
      const run = (n, d, km) => ({ id:'r'+n, dato:d, uke:'2026-27', oktnavn:'x', okttype:'Easy',
        treningsplan:'Runna', distanse:km, varighet:1800, tempo:360, soner:[0,0,0,0,0] });
      localStorage.setItem('lpl_cache', JSON.stringify({
        sessions: [run(1,'2026-07-06',5), run(2,'2026-07-10',7)],
        shoes: [], goals: {}, settings: { zones: [] },
        events: [{ id:'b', type:'plan', title:'Gammel blokk', date:'2026-07-01', endDate:'2026-07-20' },
                 { id:'c', type:'plan', title:'Aktiv blokk',  date:'2026-08-03', endDate:'2026-10-01' }],
        plannedSessions: [
          { id:'c1', date:'2026-07-06', okttype:'Easy',  distance:5, title:'', fromCompleted:true },
          { id:'c2', date:'2026-07-10', okttype:'Tempo', distance:7, title:'', fromCompleted:true },
          { id:'u1', date:'2026-08-05', okttype:'Easy',  distance:5, title:'' }
        ], lastUpdated: '' }));
    }""")
    pg.goto(APP)
    pg.evaluate("() => switchTab('plan')")
    pg.wait_for_timeout(500)
    idx = pg.locator('.planned-block-row').inner_text()
    check("the completion-derived block reports a COUNT", '2 økter' in idx, True)
    check("...and never a percentage", '%' in idx, False)
    check("...nor a ratio that flatters", 'av' in idx, False)
    # The active block, whose rows came from upcoming events, keeps a real percentage.
    head = pg.locator('#plannedAdherence').inner_text()
    check("an upcoming-derived block still measures normally",
          'økter i planen' in head or '%' in head, True)
    # And the helper itself says so, so the rule is testable without going through the DOM.
    m = pg.evaluate("() => { const t = localISODate(); const rows = Store.data.plannedSessions"
                    ".filter(p => p.date < '2026-07-20'); const a = plannedAdherence(rows, t);"
                    " return { measurable: a.measurable, pct: a.pct, due: a.due.length, done: a.done }; }")
    check("plannedAdherence marks it unmeasurable", m['measurable'], False)
    check("...with no percentage at all", m['pct'], None)
    check("...while still counting what was due and done", [m['due'], m['done']], [2, 2])
    check("no page errors", cerr, [])
    pg.close()

    # ── 3b. The ⛽ chip: a planned run long enough to need fuelling ─────────────────────────
    # The gate is estimatedSecs ALONE. The plan states no pace target, so a 17 km row with no
    # estimate is a run of unknown duration — and duration is the entire question. Deriving a pace
    # to reach a verdict is the invention this app refuses to make, so it stays silent instead.
    # Clock is frozen at 2026-08-05 (Wednesday, ISO week 2026-32: Mon 08-03 – Sun 08-09).
    print("== the ⛽ chip on a planned session ==")
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    gerr = []
    pg.on("pageerror", lambda e: gerr.append(str(e)))
    pg.add_init_script(FREEZE)
    pg.goto(APP)
    pg.evaluate("""() => localStorage.setItem('lpl_cache', JSON.stringify({
      sessions: [{ id:'r1', dato:'2026-08-04', uke:'2026-32', oktnavn:'x', okttype:'Easy',
                   treningsplan:'Runna', distanse:5, varighet:1800, tempo:360, soner:[0,0,0,0,0] }],
      shoes: [], goals: {}, settings: { zones: [] },
      events: [{ id:'b', type:'plan', title:'Blokk', date:'2026-08-03', endDate:'2026-10-01' }],
      plannedSessions: [
        { id:'f1', date:'2026-08-06', okttype:'Long', distance:17, title:'Long Run', estimatedSecs:7200 },
        { id:'f2', date:'2026-08-08', okttype:'Long', distance:16, title:'Long Run', estimatedSecs:6900 },
        { id:'f3', date:'2026-08-07', okttype:'Easy', distance:6,  title:'Easy Run', estimatedSecs:2400 },
        { id:'f4', date:'2026-08-09', okttype:'Long', distance:15, title:'Ukjent varighet' },
        { id:'f5', date:'2026-08-04', okttype:'Long', distance:18, title:'Allerede forbi', estimatedSecs:8000 },
        { id:'f6', date:'2026-08-12', okttype:'Long', distance:19, title:'Neste uke', estimatedSecs:8100 }
      ], lastUpdated: '' }));""")
    pg.goto(APP)
    pg.evaluate("() => switchTab('plan')")
    pg.wait_for_timeout(500)

    chips = pg.evaluate("() => [...document.querySelectorAll('#plannedList [data-fuel-secs]')]"
                        ".map(c => c.dataset.fuelKm)")
    check("a long upcoming run with an estimate gets the chip", "17" in chips, True)
    check("a short one does not", "6" not in chips, True)
    check("⚠️ a long one with NO estimate does not — no pace is invented", "15" not in chips, True)
    check("a past one does not, however long", "18" not in chips, True)
    check("...and nothing else sneaks in", sorted(chips), ["16", "17", "19"])

    head = pg.locator('#plannedAdherence').inner_text()
    check("the weekly line counts only THIS week's qualifying runs", "⛽ 2 økter" in head, True)
    check("...and says what the count means", "fueling er aktuelt" in head, True)

    # The chip is a jump, and the jump has to arrive loaded — landing on an empty calculator would
    # leave him retyping what the plan already knows.
    pg.click("#plannedList [data-fuel-secs]")
    pg.wait_for_timeout(500)
    check("clicking lands on Verktøy",
          pg.evaluate("() => document.querySelector('.panel.active')?.id"), "panel-tools")
    check("...with the planned distance and duration already in",
          (pg.input_value("#fuDist"), pg.input_value("#fuTime")), ("17", "2:00:00"))
    check("...and the card has answered", "geler" in pg.inner_text("#fuHero"), True)
    # The plan already knows what KIND of session it is, so the card should not have to be told
    # twice — and getting this wrong is the whole bug that made the calculator useless for his easy
    # runs. Still a push of a plain string, so the no-Store rule holds.
    check("the chip carries the session type", pg.evaluate(
        "() => [...document.querySelectorAll('#plannedList [data-fuel-secs]')]"
        ".every(c => c.dataset.fuelType)"), True)
    check("...and a Long lands on the easy ladder", pg.input_value("#fuEffort"), "rolig")
    pg.evaluate("() => switchTab('plan')")
    pg.wait_for_timeout(300)
    pg.evaluate("""() => { Store.data.plannedSessions.find(p => p.id === 'f1').okttype = 'Race';
        Settings.renderPlannedList(); }""")
    pg.wait_for_timeout(200)
    pg.click("#plannedList [data-fuel-type='Race']")
    pg.wait_for_timeout(400)
    check("...while a Race lands on the hard one", pg.input_value("#fuEffort"), "lop")
    check("...and the two ladders really disagree about that run",
          "geler" in pg.inner_text("#fuHero"), True)

    # The list re-renders on every import, match and expand. A listener bound per render would fire
    # once per redraw — invisible until the day it prefills three times and the mode flickers.
    calls = pg.evaluate("""() => {
      switchTab('plan'); Settings.renderPlannedList(); Settings.renderPlannedList();
      let n = 0; const real = FuelCalc.prefill.bind(FuelCalc);
      FuelCalc.prefill = (...a) => { n++; return real(...a); };
      document.querySelector('#plannedList [data-fuel-secs]').click();
      FuelCalc.prefill = real;
      return n;
    }""")
    check("one click is one jump, however often the list was redrawn", calls, 1)

    # Silent at zero: most weeks hold nothing long enough, and a standing "0 økter" would be noise
    # on every one of them.
    pg.evaluate("""() => { Store.data.plannedSessions = Store.data.plannedSessions
        .filter(p => p.id === 'f3'); Settings.renderPlannedList(); }""")
    pg.wait_for_timeout(200)
    check("no qualifying run means no line at all",
          "⛽" in pg.locator('#plannedAdherence').inner_text(), False)
    check("no chip page errors", gerr, [])
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
    # A SAME-type run more than a day early (his call B, 2026-10-04): it completes the session only once
    # the planned day has PASSED. While the session is still ahead it must not — an extra easy on
    # Monday would otherwise tick off Thursday's planned easy before he has run it, the 12.08 false
    # «done» again (test_weeknow caught exactly that: «✓ I dag» for a run not yet run). Once the day is
    # over, a session he moved earlier in the week is credited. The clock here is frozen at 05.08.2026,
    # so the 10.–16.08 week is AHEAD and 27.07–02.08 has passed.
    check("ahead: Mon Long does NOT yet complete Wed's Long — two days early, the day still to come",
          matched({'dato': '2026-08-10', 'okttype': 'Long'}), False)
    check("passed: Mon Long DOES complete the Wed's Long it was moved from — same week, day over",
          matched({'dato': '2026-07-27', 'okttype': 'Long'}, planned_date='2026-07-29'), True)
    check("...Mon intervals still do not, day over or not",
          matched({'dato': '2026-07-27', 'okttype': 'Intervaller'}, planned_date='2026-07-29'), False)
    check("...and the week is still the limit: the Sunday before is another week",
          matched({'dato': '2026-07-26', 'okttype': 'Long'}, planned_date='2026-07-29'), False)

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

    # ── FLAGS ARE LOCAL — the privacy fix, made executable ──────────────────────────────────
    # Until 2026-08-27 every flag was <img src="https://flagcdn.com/h24/{cc}.png">, so opening
    # Løpeatlas told a third party your IP and the exact set of countries you had run in. In an app
    # that is otherwise entirely local that was the only outbound thing describing the user, and
    # travel history is the most sensitive thing this app derives.
    print("== flags never leave the machine ==")
    ferr, freq = [], []
    pg = b.new_page(viewport={"width": 1100, "height": 900})
    pg.on("pageerror", lambda e: ferr.append(str(e)))
    # Watch EVERY http(s) request, not just flagcdn — swapping one CDN for another would sail past a
    # check that only knew the old hostname.
    pg.on("request", lambda r: freq.append(r.url) if r.url.startswith("http") else None)
    pg.goto(APP)
    pg.evaluate("""() => {
      const S = (id, d, land) => ({ id, dato:d, uke:'', oktnavn:'Tur', okttype:'Easy',
        treningsplan:'Egentrening', varighet:1800, distanse:5, tempo:360,
        soner:[0,600,600,0,0], land, lopetype:'utendors' });
      localStorage.setItem('lpl_cache', JSON.stringify({
        sessions:[S('a','2026-03-02',''), S('b','2026-04-06','PH'), S('c','2026-05-11','FR'),
                  S('d','2026-06-15','SE'), S('e','2026-07-20','JP'), S('f','2026-08-03','BR')],
        shoes:[], goals:{}, settings:{zones:[]}, events:[], plannedSessions:[], lastUpdated:'' }));
    }""")
    pg.goto(APP); pg.wait_for_timeout(600)
    # The version footer asks api.github.com for the deployed commit — but a copy opened from DISK has no
    # deployment to report, so from file:// it must not ask at all. On 2026-09-14 that ping turned CI red:
    # five "no page errors" checks in this file failed, each one this request blocked by access control —
    # over a network call nothing here is about. It never reproduced locally (Playwright 1.61 and 1.62
    # both pass), so the failure depends on how GitHub answers the CI runner's network. That is exactly
    # why this asserts on the REQUEST, not on an error: it holds on any network and any Playwright.
    check("a local copy never pings the GitHub API on load",
          [u for u in freq if "api.github.com" in u], [])
    freq.clear()                              # ignore the rest of page-load chatter (Chart.js CDN)
    pg.evaluate("() => switchTab('atlas')")
    pg.wait_for_timeout(900)
    check("⚠️ rendering the atlas makes NO outbound request", freq, [])

    imgs = pg.evaluate("""() => [...document.querySelectorAll('#panel-atlas img')]
        .map(i => ({ data: i.src.startsWith('data:'), ok: i.complete && i.naturalWidth > 0,
                     lazy: i.loading === 'lazy',
                     seen: i.getBoundingClientRect().top < window.innerHeight }))""")
    check("...and it really did render flags", len(imgs) > 0, True)
    check("every flag is an inline data URI", all(i["data"] for i in imgs), True)

    # ⚠️ A malformed SVG still produces a perfectly valid data: URI, so the URI proves nothing about
    # whether anything DRAWS. Checked per entry, off-DOM, rather than by inspecting rendered <img>s:
    # the first version filtered to images inside the viewport (the rest are loading="lazy" and
    # legitimately pending), which meant an unclosed tag in the Norwegian flag sailed through because
    # that chip happened to sit below the fold. Layout decided what got tested. This does not.
    wellformed = pg.evaluate("""() => Object.fromEntries(Object.entries(FLAG_SVG).map(([c, s]) =>
        [c, !new DOMParser().parseFromString(s, 'image/svg+xml').querySelector('parsererror')]))""")
    bad = [c for c, ok in wellformed.items() if not ok]
    check("every flag is well-formed SVG", bad, [])
    decoded = pg.evaluate("""async () => {
      const out = {};
      for (const c of Object.keys(FLAG_SVG)) {
        out[c] = await new Promise(res => {
          const i = new Image();
          i.onload  = () => res(i.naturalWidth > 0 && i.naturalHeight > 0);
          i.onerror = () => res(false);
          i.src = landFlagUrl(c);
        });
      }
      return out;
    }""")
    check("...and every one actually decodes to pixels",
          [c for c, ok in decoded.items() if not ok], [])
    check("...on every entry, not just the ones on screen", len(decoded) == len(wellformed) and len(decoded) > 0, True)

    known = pg.evaluate("() => Object.keys(FLAG_SVG)")
    check("every entry is a real ISO-3166 alpha-2 code",
          all(len(k) == 2 and k.isupper() for k in known), True)
    for c in known:
        u = pg.evaluate("(c) => landFlagUrl(c)", c)
        check(f"{c} resolves to an inline SVG", bool(u and u.startswith("data:image/svg+xml,")), True)
    # ⚠️ THE ACCEPTED TRADE-OFF. flagcdn answered for all ~250 countries; this set carries only the
    # ones actually run in. An unlisted country falls back to the browser's own flag emoji (since
    # 2026-09-18) and, where the browser has none, to its NAME — never vanishing, never a broken image.
    # Which branch applies is the ENGINE's answer, so read it rather than assume it: CI's WebKit on
    # Windows has no flag emoji (like Windows Chrome/Edge), Firefox and Apple devices do. Either way
    # nothing is fetched — the request watch above covers this path too.
    emoji = pg.evaluate("() => !!emojiFlagUrl('DE')")
    br_url = pg.evaluate("() => landFlagUrl('BR')")
    check("an unlisted country: emoji PNG where the browser has flags, else none",
          (br_url or "").startswith("data:image/png") if emoji else br_url, True if emoji else None)
    # ZZ is a pair of regional-indicator letters with no flag behind it. Firefox's emoji font draws
    # it as two COLOURED letter boxes, which a colour test alone took for a flag (caught 2026-09-18).
    check("...and gibberish is never mistaken for a flag", pg.evaluate("() => landFlagUrl('ZZ')"), None)
    chips = pg.evaluate("""() => [...document.querySelectorAll('.land-chip')].map(c =>
        ({ text: c.innerText.replace(/\\s+/g, ' ').trim(), flag: !!c.querySelector('img') }))""")
    br = [c for c in chips if c["text"].startswith("Brasil")]
    check("...and the country is always NAMED, flagged only if the browser can",
          (len(br), br and br[0]["flag"]), (1, emoji))
    check("...while a known one keeps its flag",
          [c["flag"] for c in chips if c["text"].startswith("Norge")], [True])
    check("no flag page errors", ferr, [])
    pg.close()

    # ── HTML ESCAPING, swept rather than spot-checked ────────────────────────────────────────
    # Found by the 2026-08-27 privacy audit: `prevBlock.title` reached innerHTML raw in the block
    # comparison, while every sibling line escaped. A hand-typed block name, so self-XSS rather than a
    # remote hole — but the origin it would run on is psvadev.github.io, which holds the Drive and
    # Strava tokens in localStorage, and a GitHub Pages user site shares that origin with every other
    # project published under the same account.
    #
    # Written as a SWEEP, not one assertion about that line. The bug was not "this template forgot a
    # call", it was "nothing anywhere checked", so pinning the one line would leave the next omission
    # just as invisible. The payload is an <img> with a broken src: if it is ever inserted as markup
    # rather than text, the browser fires onerror by itself — no click, no timing, no guessing which
    # surface renders it.
    print("== hand-typed names are escaped everywhere they render ==")
    xerr = []
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    pg.on("pageerror", lambda e: xerr.append(str(e)))
    pg.on("dialog", lambda d: d.accept())
    PAYLOAD = '<img src=x onerror="window.__xss=1">'
    pg.goto(APP)
    pg.evaluate("""(p) => {
      const S = (id, d, typ, km) => ({ id, dato:d, uke:'', oktnavn:p, okttype:typ, treningsplan:'Runna',
        varighet: km*360, distanse: km, tempo:360, soner:[0,600,600,0,0], notater:p,
        // `land` carries the payload too (added 2026-09-09). The form refuses an unknown country
        // since 2026-09-18, but data saved before then can still hold free text, so every render
        // site must keep escaping it (detail panel, atlas chips and lists, panel title, datalist);
        // this is what makes that a checked fact rather than a lucky one.
        beskrivelse:p, land:p, sko:p, lopetype:'utendors' });
      localStorage.setItem('lpl_cache', JSON.stringify({
        sessions: [S('x','2026-04-06','Easy',5),  S('y','2026-04-13','Long',9),
                   S('a','2026-06-05','Easy',5),  S('b','2026-06-12','Long',10),
                   S('c','2026-08-06','Easy',5),  S('d','2026-08-13','Long',12)],
        shoes: [{ name:p, startKm:0, retired:false }],
        customSessionTypes: [p], customPlans: [p],
        goals: { '2026': 900 }, distanceGoals: { '5k': 1500 },
        settings: { zones: [] },
        // ⚠️ THREE blocks, and the sessions above span the first two. The comparison panel — where the
        // bug actually was — renders only for a block that is BOTH finished and preceded by another
        // (`prevBlock && !isCurrent`). Two blocks where the second is still running produces no
        // comparison at all, which is how the first version of this sweep passed with the fix
        // reverted: it walked every tab and clicked every list, and never once reached the markup.
        events: [
          { id:'b0', type:'plan', title:p, date:'2026-04-01', endDate:'2026-05-15' },
          { id:'b1', type:'plan', title:p, date:'2026-06-01', endDate:'2026-07-15' },
          { id:'b2', type:'plan', title:p, date:'2026-08-03', endDate:'2026-10-01' },
          { id:'r1', type:'race', title:p, date:'2026-10-01', distanceKm:10 },
          { id:'i1', type:'illness', title:p, date:'2026-07-20', endDate:'2026-07-22' }],
        plannedSessions: [{ id:'p1', date:'2026-08-06', okttype:'Easy', distance:5, title:p }],
        lastUpdated:'' }));
    }""", PAYLOAD)
    pg.goto(APP)
    pg.wait_for_timeout(700)

    for tab in ['dash', 'log', 'atlas', 'plan', 'tools', 'settings']:
        pg.evaluate("(t) => switchTab(t)", tab)
        pg.wait_for_timeout(350)
    # Every drill-down, through the real click path.
    pg.evaluate("() => switchTab('dash')")
    pg.wait_for_timeout(500)
    saw_comparison = False
    # '.rk-prow[role=button]', not the old '.record-card': the Rekorder redesign (2026-09-27) would
    # otherwise have left this walk clicking NOTHING in Rekorder, silently narrowing the sweep.
    for sel in ['#weeklyTable tbody tr', '.rk-prow[role=button]', '#blocksCard [data-block]']:
        loc = pg.locator(sel)
        for i in range(min(loc.count(), 4)):
            loc.nth(i).click()
            pg.wait_for_timeout(400)
            # ⚠️ innerHTML, not innerText. The detail modal scrolls, and innerText returns only what
            # is RENDERED — the comparison section sits below the fold, so innerText omitted it and
            # this read False on the one block that had it. Same family as is_visible() on an empty
            # div: an API that quietly answers about layout when you asked about content.
            if "Sammenlignet med" in pg.evaluate("() => document.getElementById('detailBody').innerHTML"):
                saw_comparison = True
            pg.keyboard.press("Escape")
            pg.wait_for_timeout(150)

    # ⚠️ The SESSION detail panel, added 2026-09-09, and the reason is a falsification result:
    # breaking `${raw ? v : escapeHtml(v)}` in that panel failed NOTHING. The walk above clicks week
    # rows, record cards and block cards, and never once opened a session — so the panel that renders
    # Land, Sko, Øktbeskrivelse and Notater, four user-typed fields, was outside the sweep entirely.
    # Clicking a log row is the real path (Log.rowClick → DetailPanel.openSession).
    pg.evaluate("() => switchTab('log')")
    pg.wait_for_timeout(400)
    saw_session = False
    rows = pg.locator('#logBody tr')
    for i in range(min(rows.count(), 3)):
        rows.nth(i).click()
        pg.wait_for_timeout(350)
        if "dp-" in pg.evaluate("() => document.getElementById('detailBody').innerHTML"):
            saw_session = True
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(150)
    check("a session detail panel actually opened", saw_session, True)

    # ⚠️ The comparison markup MUST have rendered, or everything below is vacuous. Asserted rather
    # than assumed, twice over: the first version of this sweep clicked four lists, reached the panel
    # through none of them, and passed cleanly with the escape fix reverted. The second clicked the
    # LAST block — the oldest, which has nothing before it to compare against. Hence every block, and
    # a flag, rather than an index anyone would have to keep in step with the render order.
    check("the block comparison panel actually opened", saw_comparison, True)

    check("⚠️ no injected element executed anywhere",
          pg.evaluate("() => window.__xss || 0"), 0)
    check("...and none was even created as markup",
          pg.evaluate("() => document.querySelectorAll('img[onerror]').length"), 0)
    # Proof the sweep actually met the payload — without this it would pass just as happily on a page
    # that rendered none of the seeded names, which is the vacuous version of this whole section.
    # innerHTML again, and escaped: a correctly-escaped payload appears as &lt;img, so THAT is the
    # string to look for. Finding it proves the names reached the DOM and were neutralised there.
    check("...while the payload really did reach the DOM, escaped",
          pg.evaluate("() => document.body.innerHTML.includes('&lt;img src=x onerror=')"), True)
    check("no page errors", xerr, [])
    pg.close()

    # ── Legacy plan rows recover their provenance ────────────────────────────────────────────────
    # `fromCompleted` shipped 2026-08-18 with the adherence guard, but nothing backfilled the rows
    # already in the file. A missing field is falsy, which reads as "captured while still upcoming" —
    # the exact opposite of the truth for a row rebuilt from a COMPLETED event. One such row defeats
    # `due.every(p => p.fromCompleted)`, so the guard silently no-opped on the very block it was
    # written for: Runna 10K #1 reported "33 av 33 fullført · 100%" for a plan in which a miss could
    # never have been recorded. The guard was right; the data was never migrated to match it.
    print("== legacy plan rows recover fromCompleted ==")
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    merr = []
    pg.on("pageerror", lambda e: merr.append(str(e)))
    pg.add_init_script(FREEZE)
    pg.goto(APP)
    pg.evaluate("""() => {
      // `id` is load-bearing: matchPlannedSessions stores the ACTUAL's id as the match value, so an
      // id-less run matches and still reads as undefined — a silent zero for `done`.
      const run = (d, t, km) => ({ id:'s'+d.replace(/-/g,''), dato:d, okttype:t, distanse:km,
                                   varighet:1800, treningsplan:'Runna', sted:'Ute' });
      localStorage.setItem('lpl_cache', JSON.stringify({
        sessions: [run('2026-06-03','Easy',5), run('2026-06-05','Long',8), run('2026-06-10','Easy',5)],
        shoes: [], goals: {}, settings: { zones: [] },
        events: [{ id:'b', type:'plan', title:'Runna 10K #1', date:'2026-06-01', endDate:'2026-06-30' }],
        plannedSessions: [
          // Bare activityId — a COMPLETED event's id shape — and no fromCompleted field at all.
          // These are the real thing: ids copied from the shape his own 10K #1 rows turned out to have.
          { id:'d493bc72-89b9-446c-9886-8d6a06592efb', date:'2026-06-03', okttype:'Easy', distance:5, title:'' },
          { id:'7424665d-faef-4c08-9c03-3a3fac356c67', date:'2026-06-05', okttype:'Long', distance:8, title:'' },
          { id:'cf21c286-a811-4524-a790-efe20b5d4f1b', date:'2026-06-10', okttype:'Easy', distance:5, title:'' },
          // An UPCOMING event's id keeps its "_plan_week_N_TYPE_i" suffix. Legacy as well, but
          // genuinely prospective — dated ahead of FREEZE so it stays 'pending' and out of `due`.
          { id:'898ccdf5-84d7-4ed9-9d7c-2373b2de9330_plan_week_3_EASY_0',
            date:'2026-09-01', okttype:'Easy', distance:5, title:'' },
          // Bare id, but already knows its provenance. The migration fills only `undefined`, so
          // flipping this to true would mean it is overwriting rows that already have an answer.
          { id:'5606034f-fa4d-4b48-90ca-e89994a701da', date:'2026-09-03', okttype:'Long',
            distance:9, title:'', fromCompleted:false }
        ], lastUpdated: '' }));
    }""")
    pg.goto(APP)
    pg.wait_for_timeout(300)

    # Positive control FIRST: every assertion below reads off Store, and all of them pass just as
    # happily against an empty one. This is the line that says the fixture actually loaded.
    check("the seeded plan really loaded", pg.evaluate("() => Store.data.plannedSessions.length"), 5)

    prov = pg.evaluate("() => Store.data.plannedSessions.map(p => p.fromCompleted)")
    check("rows rebuilt from completions are marked fromCompleted", prov[:3], [True, True, True])
    check("...an UPCOMING-shaped id is not", prov[3], False)
    check("...and a row that already knew is left alone", prov[4], False)

    adh = pg.evaluate("() => { const r = plannedAdherence(Store.data.plannedSessions, '2026-08-05'); "
                      "return { pct: r.pct, measurable: r.measurable, due: r.due.length, done: r.done }; }")
    check("a plan rebuilt from completions reports no percentage",
          (adh["measurable"], adh["pct"]), (False, None))
    check("...while still counting the sessions it does know about",
          (adh["due"], adh["done"]), (3, 3))

    # The falsification, run in-page rather than by breaking the source: with the field falsy — which
    # is precisely the pre-migration state — the same rows claim a perfect score. Without this the
    # assertion above would pass just as well if `plannedAdherence` returned null unconditionally.
    ctrl = pg.evaluate("""() => {
      const rows = Store.data.plannedSessions.map(p => ({ ...p, fromCompleted: undefined }));
      const r = plannedAdherence(rows, '2026-08-05');
      return { pct: r.pct, measurable: r.measurable };
    }""")
    check("control: un-migrated, the same rows would claim 100%",
          (ctrl["measurable"], ctrl["pct"]), (True, 100))

    check("no page errors", merr, [])
    pg.close()

    # ── 5. The plan prefill: what it fills, when it refuses, and what it takes back ──────────
    # Reported 2026-09-07 as Øktbeskrivelse "lingering" after logging the day's run, surviving
    # reloads and appearing on every device. None of that was persistence: applyPlannedDefault()
    # re-derives from the synced plan every time the form opens, and save() ends in clear(), which
    # runs it again for today's date — so logging the planned run put the prescription straight back
    # into the emptied form.
    print("== plan prefill: fill, refuse, withdraw ==")
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    perr = []
    pg.on("pageerror", lambda e: perr.append(str(e)))
    pg.add_init_script(FREEZE)
    BESK = "Oppvarming 10 min\n5 km rolig\nNedjogg 5 min"
    pg.goto(APP)
    pg.evaluate("""([besk]) => localStorage.setItem('lpl_cache', JSON.stringify({
        sessions: [{ id: 'logged', dato: '2026-08-06', okttype: 'Long', distanse: 12,
                     varighet: 4200, soner: [0,0,0,0,0], løpetype: 'utendors' }],
        shoes: [], shoeDefaults: {}, goals: {}, events: [], customSessionTypes: [], customPlans: [],
        plannedSessions: [
          { id: 'p1', date: '2026-08-05', okttype: 'Easy', distance: 6.5,
            title: 'Runna Easy', beskrivelse: besk },
          { id: 'p2', date: '2026-08-06', okttype: 'Long', distance: 12,
            title: 'Runna Long', beskrivelse: 'Langtur 12 km' }],
        consistencySettings: { kmThreshold: 15, runThreshold: 2 },
        settings: { maxHR: 195, zones: [] }, lastUpdated: ''
    }))""", [BESK])
    pg.goto(APP)
    pg.evaluate("() => switchTab('form')")
    pg.wait_for_timeout(400)

    def setdate(d):
        pg.evaluate("""d => { const el = document.getElementById('fDato'); el.value = d;
                              el.dispatchEvent(new Event('change', { bubbles: true })); }""", d)
        pg.wait_for_timeout(200)

    def form():
        return pg.evaluate("""() => ({
            besk: document.getElementById('fBeskrivelse').value,
            mal:  document.getElementById('fMalDistanse').value,
            hint: document.getElementById('planPrefillHint').textContent })""")

    # ⚠️ POSITIVE CONTROL FIRST. Everything below asserts that fields are EMPTY, which is also what
    # a form that never prefilled at all would show. This is the only line proving there is a
    # mechanism to withdraw.
    setdate("2026-08-05")
    f = form()
    check("control: an unlogged planned date fills beskrivelse", f["besk"], BESK)
    check("...and Mål distanse", f["mal"], "6.5")
    check("...and names the source", "Fra planen" in f["hint"], True)

    # The bug found while investigating: moving to a date with no plan used to leave both values
    # sitting there while the 📋 hint — the one thing naming their source — disappeared.
    setdate("2026-08-07")
    f = form()
    check("a date with no plan withdraws the prescription", f["besk"], "")
    check("...and the target distance", f["mal"], "")
    check("...and clears the hint", f["hint"], "")

    # The reported bug: the day's planned run is already logged, so the prescription must not come
    # back. This is the state save() → clear() lands in.
    setdate("2026-08-06")
    f = form()
    check("an already-logged planned date does not prefill", f["besk"], "")
    check("...nor its distance", f["mal"], "")
    check("...and stays silent about the plan", f["hint"], "")
    # Distinguish "refused because logged" from "refused because it cannot find the plan at all":
    # without this, deleting the lookup entirely would pass every assertion above.
    check("control: that date really does have a planned session",
          pg.evaluate("() => Store.data.plannedSessions.some(p => p.date === '2026-08-06')"), True)

    # Withdrawal must never touch what you typed. Only the exact value the prefill wrote is taken
    # back — anything edited by hand, or filled from Strava, no longer matches and survives.
    setdate("2026-08-05")
    check("control: prefill fired again", form()["besk"], BESK)
    pg.evaluate("() => { document.getElementById('fBeskrivelse').value = 'Mine egne ord'; }")
    setdate("2026-08-07")
    check("a hand-edited beskrivelse is NOT withdrawn", form()["besk"], "Mine egne ord")

    check("no page errors", perr, [])
    pg.close()

    # ── 5b. A fetched run finds ITS planned session, also on another day of the week (2026-10-04) ──
    # His report: the long run moved to Sunday arrived as «Easy» / «Runna Easy» with no Øktbeskrivelse,
    # although Strava said «12km Long Run». The plan was only looked up by the form's DATE, and the
    # title — Runna's record of the workout he started — was thrown away as «generic». Now the title is
    # the evidence: a generic one gives the TYPE, a named one must equal the plan's title, and the
    # planned session that fits, not yet run, in the same ISO week, supplies type, Mål distanse and
    # Øktbeskrivelse. With no such session the title's type still sets Økt-type.
    print("== a fetched run finds its planned session within the week ==")
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    perr = []
    pg.on("pageerror", lambda e: perr.append(str(e)))
    pg.add_init_script(FREEZE)
    pg.goto(APP)
    pg.evaluate("""() => localStorage.setItem('lpl_cache', JSON.stringify({
        sessions: [{ id: 'done', dato: '2026-09-29', okttype: 'Easy', treningsplan: 'Runna', distanse: 7,
                     varighet: 2700, soner: [0,0,0,0,0], løpetype: 'utendors' }],
        shoes: [], shoeDefaults: {}, goals: {}, events: [], customSessionTypes: [], customPlans: [],
        plannedSessions: [
          { id: 'pE',  date: '2026-09-29', okttype: 'Easy', distance: 7,  title: 'Easy Run', beskrivelse: 'Rolig 7 km' },
          { id: 'pI',  date: '2026-10-01', okttype: 'Intervaller', distance: 8, title: 'Pyramid Intervals', beskrivelse: 'Pyramide 1-2-3-2-1' },
          { id: 'pL',  date: '2026-10-03', okttype: 'Long', distance: 12, title: 'Long Run', beskrivelse: 'Langtur 12 km rolig' },
          { id: 'pE2', date: '2026-10-04', okttype: 'Easy', distance: 6,  title: 'Easy Run', beskrivelse: 'Rolig 6 km' }],
        consistencySettings: { kmThreshold: 15, runThreshold: 2 },
        settings: { maxHR: 195, zones: [] }, lastUpdated: ''
    }))""")
    pg.goto(APP)
    pg.evaluate("""() => { switchTab('form');
      StravaIO.fetchActivityDetail = async () => ({ description: '' }); StravaIO.fetchZones = async () => null; }""")
    pg.wait_for_timeout(400)
    FETCH = """async ([date, title, km]) => {
      Form.clear();
      const d = document.getElementById('fDato'); d.value = date; d.dispatchEvent(new Event('change'));
      await StravaImport._populate({ id: 7, name: title, distance: km * 1000, moving_time: km * 400,
                                     average_speed: 2.5, trainer: false, has_heartrate: false });
      const v = id => document.getElementById(id).value;
      return { type: v('fOkttype'), name: v('fOktnavn'), mal: v('fMalDistanse'), besk: v('fBeskrivelse'),
               hint: document.getElementById('planPrefillHint').textContent };
    }"""
    def fetched(date, title, km=12):
        return pg.evaluate(FETCH, [date, title, km])

    # Positive control: on the planned date with a title that says nothing, the date's plan fills —
    # as before. Without it, every «does not fill» below would pass on a prefill that never runs.
    f = fetched("2026-10-04", "Sunday Morning Run", 6)
    check("control: a title with no workout in it → the DATE's plan, as before",
          (f["type"], f["mal"], f["besk"]), ("Easy", "6", "Rolig 6 km"))
    f = fetched("2026-10-04", "12km Long Run")
    check("⚠️ his run: Sunday's «12km Long Run» is Saturday's planned long run, not Sunday's easy",
          (f["type"], f["name"], f["mal"], f["besk"]), ("Long", "Runna Long", "12", "Langtur 12 km rolig"))
    check("...and the 📋 line says it was planned for another day", "planlagt lørdag 03.10.2026" in f["hint"], True)
    f = fetched("2026-09-30", "Pyramid Intervals", 8)
    check("a NAMED workout on a day with no plan finds its session by name",
          (f["type"], f["name"], f["besk"]), ("Intervaller", "Pyramid Intervals", "Pyramide 1-2-3-2-1"))
    # Wednesday: Tuesday's easy is the NEARER one (1 day vs 4), so only the «already done» rule can
    # send this run to Sunday's — on Friday the distance alone would, and the check could not fail.
    f = fetched("2026-09-30", "Easy Run", 7)
    check("a session already run is not handed out twice — Tuesday's easy is done, so Sunday's",
          f["besk"], "Rolig 6 km")
    f = fetched("2026-10-06", "10km Long Run", 10)
    check("another week's plan is never borrowed — the title still sets the type",
          (f["type"], f["name"], f["mal"], f["besk"], f["hint"]), ("Long", "Runna Long", "", "", ""))
    f = fetched("2026-10-04", "Broken Miles", 9)
    check("a named workout the plan does not have changes nothing — the date's plan, as before",
          (f["type"], f["besk"]), ("Easy", "Rolig 6 km"))
    check("no page errors", perr, [])
    pg.close()

    # ── 5c. «Avbrutt»: a run stopped part-way is not a completed session (2026-10-05) ──────────────
    # His report: an interval run stopped at 5.3 of 9 km for calf pain showed green ✓ everywhere the
    # plan is shown. «Avvik» could not help — it is about DATA QUALITY (keep it out of the trends), and
    # a run with a faulty strap is Avvik yet fully completed. «Avbrutt» is its own field, set by hand
    # (never inferred from distance: a long run shortened on purpose is not aborted). An aborted run
    # still holds its planned session — status 'partial', ◐ with km run against km planned — counts as
    # NOT completed in adherence (his pick, over «half»), and is named beside the % like «unntatt».
    # A complete run of the same type later that week takes the session from it (a make-up).
    print("== «Avbrutt»: started, not completed ==")
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    perr = []
    pg.on("pageerror", lambda e: perr.append(str(e)))
    pg.add_init_script(FREEZE)          # 05.08.2026: both weeks below are over
    pg.goto(APP)
    pg.evaluate("""() => {
      const run = (id, d, type, km, extra) => Object.assign({ id, dato:d, uke:'', oktnavn:'x', okttype:type,
        treningsplan:'Runna', distanse:km, varighet:km * 380, tempo:380, soner:[0,0,0,0,0] }, extra || {});
      localStorage.setItem('lpl_cache', JSON.stringify({
        sessions: [run('t1','2026-07-21','Tempo',3,{ avbrutt:true }), run('t2','2026-07-22','Tempo',7),
                   run('a1','2026-07-27','Intervaller',5.3,{ avbrutt:true }), run('a2','2026-07-29','Easy',8)],
        shoes: [], goals: {}, settings: { zones: [] }, customSessionTypes: [], customPlans: [],
        events: [{ id:'c', type:'plan', title:'Runna 10K #2', date:'2026-07-20', endDate:'2026-10-01' }],
        plannedSessions: [
          { id:'pT', date:'2026-07-21', okttype:'Tempo',       distance:7,  title:'' },
          { id:'pI', date:'2026-07-27', okttype:'Intervaller', distance:9,  title:'Broken Miles' },
          { id:'pE', date:'2026-07-29', okttype:'Easy',        distance:8,  title:'' },
          { id:'pL', date:'2026-07-31', okttype:'Long',        distance:13, title:'' }], lastUpdated: '' }));
    }""")
    pg.goto(APP)
    st = pg.evaluate("""() => { const pl = Store.data.plannedSessions, m = matchPlannedSessions(pl), t = localISODate();
      const a = plannedAdherence(pl, t);
      return { status: Object.fromEntries(pl.map(p => [p.id, plannedStatus(p, m, t)])),
               pT: m.pT, due: a.due.length, done: a.done, partial: a.partial, pct: a.pct }; }""")
    check("the aborted interval session is 'partial' — not done, not missed", st["status"]["pI"], "partial")
    check("a make-up Tempo the next day takes its session from the aborted one", (st["pT"], st["status"]["pT"]), ("t2", "done"))
    check("adherence: 2 of 4 completed, 50% — the aborted one is due and NOT completed",
          (st["due"], st["done"], st["pct"]), (4, 2, 50))
    check("...and counted apart, as its own number", st["partial"], 1)
    pg.evaluate("() => { switchTab('plan'); Settings.renderPlannedList(); }")
    pg.wait_for_timeout(300)
    head = pg.locator('#plannedAdherence').inner_text()
    check("Planlegging: «2 av 4 … fullført · 50%» and «1 avbrutt» beside it",
          ("2 av 4" in head, "50%" in head, "1 avbrutt" in head), (True, True, True))
    rowI = pg.evaluate("""() => [...document.querySelectorAll('#plannedList > div')]
        .map(r => r.innerText).find(t => t.includes('Broken Miles')) || ''""")
    check("...its row reads ◐ with the km run against the km planned", ("◐" in rowI, "5.3 av 9 km" in rowI), (True, True))
    pg.evaluate("() => switchTab('dash')")
    pg.wait_for_timeout(400)
    card = pg.locator('#blocksCard').inner_text()
    check("Dashboard block card: the same «2 av 4 fullført · 50%» and «1 avbrutt»",
          ("2 av 4 fullført · 50%" in card, "1 avbrutt" in card), (True, True))
    # The form: one checkbox, round-tripped, absent from the JSON when unticked (like utenforAnalyse).
    form = pg.evaluate("""() => { switchTab('form'); Form.clear();
      const box = document.getElementById('fAvbrutt'); if (!box) return 'missing';
      const off = Form.read().avbrutt; box.checked = true; const on = Form.read().avbrutt;
      Form.clear(); const cleared = box.checked;
      return { off: off === undefined, on, cleared }; }""")
    check("Form: «Avbrutt» is stored only when ticked, and clear() unticks it",
          form, {"off": True, "on": True, "cleared": False})
    check("no page errors", perr, [])
    pg.close()

    # ── Consistency pass (2026-09-27), from a review of every tab in Firefox ────────────────────
    # Each of these was a small inconsistency he had stopped seeing; each check fails if its fix is
    # reverted. Firefox itself is not in this suite (CI is WebKit-only by decision), so the Firefox
    # cases are pinned by the CSS that causes them, not by a Firefox render.
    print("== consistency pass ==")
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    perr = []
    pg.on("pageerror", lambda e: perr.append(str(e)))
    boot(pg, "plan")
    # Hendelser: ✕ means CLOSE everywhere else (detail panel, Strava dialog). Here it deleted.
    dels = pg.evaluate("() => [...document.querySelectorAll('[data-del-event]')].map(b => b.textContent.trim())")
    check("control: there are events to delete", len(dels) > 0, True)
    check("Hendelser deletes with 🗑️, the app's delete — not ✕, the app's close", set(dels), {"🗑️"})
    # The Runna import is a real button now; the raw picker printed «Browse… No file selected.»
    check("the raw file picker is hidden",
          pg.evaluate("() => getComputedStyle(document.getElementById('runnaIcsFile')).display"), "none")
    with pg.expect_file_chooser() as fc:
        pg.click("#btnPickIcs")
    check("...and the button opens it", fc.value is not None, True)
    # A form save looks like every other form save.
    pg.evaluate("() => switchTab('settings')"); pg.wait_for_timeout(300)
    check("«Lagre grenser» is the same primary save as «Lagre» and «Lagre profil»",
          pg.evaluate("""() => ['contSaveBtn', 'btnSaveConsistency', 'btnSaveProfile']
              .map(id => document.getElementById(id).classList.contains('btn-primary'))"""), [True, True, True])
    check("...and its fields get the shared field style (accent border on focus)",
          pg.evaluate("() => ['contWalkMax', 'contRunMin'].every(id => document.getElementById(id).classList.contains('inp'))"), True)
    # Firefox drew these in monospace because controls do not inherit the page font on their own.
    pg.evaluate("() => switchTab('form')"); pg.wait_for_timeout(300)
    fonts = pg.evaluate("""() => { const body = getComputedStyle(document.body).fontFamily;
        return ['fNotater', 'fBeskrivelse', 'fDato'].map(id => {
          const e = document.getElementById(id); return e ? getComputedStyle(e).fontFamily === body : null; }); }""")
    check("⚠️ notes, description and date use the page font, not the browser's", fonts, [True, True, True])
    check("number fields carry no steppers",
          pg.evaluate("() => getComputedStyle(document.querySelector('input[type=number]')).appearance"), "textfield")
    # A session is «økt»; «løp» also means race. The year table beside «Ukentlig oversikt» said LØP.
    pg.evaluate("() => switchTab('dash')"); pg.wait_for_timeout(500)
    # ⚠️ Scoped to the year table itself, and fed two years of runs. The first version read every
    # <th> on the dashboard of THIS fixture — which has no sessions, so the dashboard was its empty
    # state and the year table never rendered — found «Økter» in some other table, and passed with
    # «Løp» restored (falsification, 2026-09-27).
    pg.evaluate("""() => { const d = JSON.parse(localStorage.getItem('lpl_cache'));
        d.sessions = [
          { id:'y1', dato:'2025-10-02', uke:'2025-40', okttype:'Easy', distanse:5, varighet:1800, tempo:360, soner:[0,0,0,0,0] },
          { id:'y2', dato:'2026-03-02', uke:'2026-10', okttype:'Easy', distanse:6, varighet:2160, tempo:360, soner:[0,0,0,0,0] }];
        localStorage.setItem('lpl_cache', JSON.stringify(d)); }""")
    pg.goto(APP); pg.wait_for_timeout(500)
    pg.evaluate("() => switchTab('dash')"); pg.wait_for_timeout(600)
    heads = pg.evaluate("() => [...document.querySelectorAll('#yearCompTable th')].map(t => t.textContent.trim())")
    check("control: the year table is rendered", len(heads) > 0, True)
    check("the year table counts «Økter», not «Løp»", ("Økter" in heads, "Løp" in heads), (True, False))
    check("no page errors in the consistency pass", perr, [])
    pg.close()

    # ── A run's detail header (his pick, mockup A, 2026-09-27) ───────────────────────────────────
    # What kind of run it was is ONE line under the title, and distanse / tid / tempo lead the panel;
    # the list below is what it always was, minus the six rows that moved up. What would fail
    # silently: another panel inheriting the last run's line (the header is shared by every panel),
    # the hand-typed plan name reaching a NEW innerHTML sink raw, a sparse run growing empty tiles,
    # and a row lost on the way.
    print("== a run's detail header ==")
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    perr = []
    pg.on("pageerror", lambda e: perr.append(str(e)))
    pg.goto(APP)
    pg.evaluate("""() => localStorage.setItem('lpl_cache', JSON.stringify({
      sessions: [
        { id:'full', dato:'2026-08-05', uke:'2026-32', oktnavn:'Runna Intervaller', okttype:'Intervaller',
          treningsplan:'Runna', løpetype:'treadmill', distanse:6.92, varighet:2387, tempo:345, snittkmh:10.44,
          gjsnittspuls:158, toppuls:173, stigning:1, sko:'Nike Pegasus 41', rpe:8, soner:[334,861,620,477,95] },
        { id:'bare', dato:'2026-08-09', uke:'2026-32', oktnavn:'Tur', okttype:'Easy', løpetype:'utendors',
          varighet:1800, soner:[0,0,0,0,0] },
        { id:'long', dato:'2026-08-16', uke:'2026-33', oktnavn:'Langtur', okttype:'Long', løpetype:'utendors',
          treningsplan:'Halvmaraton sub 2 – vinterblokken med bakker', distanse:21.14, varighet:7199, tempo:341,
          soner:[0,0,0,0,0], stravaId:'16012345679' },
        { id:'strava', dato:'2026-10-01', uke:'2026-40', oktnavn:'Runna Easy', okttype:'Easy', treningsplan:'Runna',
          løpetype:'utendors', distanse:8.02, varighet:3100, tempo:387, soner:[0,0,0,0,0], stravaId:'16012345678' },
        { id:'badid', dato:'2026-10-02', uke:'2026-40', oktnavn:'x', okttype:'Easy', løpetype:'utendors',
          distanse:5, varighet:1800, tempo:360, soner:[0,0,0,0,0],
          stravaId:'1"><img src=x onerror="window.__sx=1">' },
        { id:'xss', dato:'2026-08-10', uke:'2026-33', oktnavn:'x', okttype:'Easy', løpetype:'utendors',
          treningsplan:'<img src=x onerror="window.__xss=1">', distanse:5, varighet:1800, tempo:360,
          soner:[0,0,0,0,0] }],
      shoes: [], goals: {}, events: [], plannedSessions: [], settings: { zones: [] }, lastUpdated: '' }))""")
    pg.goto(APP)
    pg.wait_for_timeout(500)
    HEAD = """(id) => {
      if (id) DetailPanel.openSession(id);
      const txt = el => el.textContent.trim().replace(/\\s+/g, ' ');
      const m = document.getElementById('detailMeta');
      return { title: txt(document.getElementById('detailTitle')), meta: m.hidden ? null : txt(m),
               lead: [...document.querySelectorAll('#detailBody .dp-lead .dp-stat')]
                       .map(s => [txt(s.querySelector('.dpv')), txt(s.querySelector('.dpl'))]),
               rows: [...document.querySelectorAll('#detailBody .dp-kv .dp-key')].map(txt) };
    }"""
    full = pg.evaluate(HEAD, 'full')
    check("the title is still the run's name", full['title'], 'Runna Intervaller')
    check("one line under it: weekday and date · type and plan · venue",
          full['meta'], 'onsdag 05.08.2026 · Intervaller Runna · Tredemølle')
    check("distance, time and pace lead the panel",
          full['lead'], [['6.92 km', 'distanse'], ['0:39:47', 'tid'], ['5:45 /km', 'tempo']])
    # Exactly the six rows that moved up are gone — the rest in their old order, nothing else lost.
    # No «Stigning» although this run stores stigning:1: the incline was retired the same day.
    check("...and the list keeps every other row, in its old order",
          full['rows'], ['Snitt km/t', 'HR snitt / topp', 'Sko', 'RPE'])
    bare = pg.evaluate(HEAD, 'bare')
    check("a run with only a time leads with only the time", bare['lead'], [['0:30:00', 'tid']])
    check("...and with no plan, the plan is simply left out", bare['meta'], 'søndag 09.08.2026 · Easy · Utendørs')
    # A link to the run on Strava, for the route and everything Puls does not keep (his ask, 2026-10-01).
    # Only from an id that is a plain number: a hand-edited file could hold anything there.
    strava = pg.evaluate(HEAD, 'strava')
    check("a run linked to Strava ends its line with «Vis på Strava ↗»",
          strava['meta'], 'torsdag 01.10.2026 · Easy Runna · Utendørs · Vis på Strava ↗')
    check("...a link to that activity, opening in a new tab",
          pg.evaluate("""() => { const a = document.querySelector('#detailMeta a');
            return a && [a.getAttribute('href'), a.target, (a.rel || '').includes('noopener')]; }"""),
          ['https://www.strava.com/activities/16012345678', '_blank', True])
    # Squeeze the line so it must break in the MIDDLE of the link: the link moves down whole instead of
    # leaving «Vis på» on one line and «Strava ↗» on the next. Measured from the link itself, so it holds
    # whatever the fonts.
    check("...and the link never splits across two lines",
          pg.evaluate("""() => { const m = document.getElementById('detailMeta'), a = m.querySelector('a');
            if (!a) return null;
            const ml = m.getBoundingClientRect().left, ar = a.getBoundingClientRect();
            m.style.width = (ar.left - ml + ar.width / 2) + 'px';
            const n = a.getClientRects().length; m.style.width = ''; return n; }"""), 1)
    pg.evaluate(HEAD, 'full')
    check("a run with no Strava id has no link",
          pg.evaluate("() => document.querySelectorAll('#detailMeta a').length"), 0)
    pg.evaluate(HEAD, 'badid')
    pg.wait_for_timeout(200)
    check("⚠️ an id that is not a plain number gives no link at all — nothing to inject",
          pg.evaluate("""() => [document.querySelectorAll('#detailMeta a').length,
                                document.querySelectorAll('#detailMeta img').length, window.__sx || 0]"""),
          [0, 0, 0])
    # The header belongs to every panel. A week opened after a run must not keep the run's line.
    pg.evaluate("() => DetailPanel.openWeek('2026-32', Store.data.sessions)")
    pg.wait_for_timeout(200)
    week = pg.evaluate(HEAD, None)
    check("control: the week panel opened", week['title'].startswith('Uke 32'), True)
    check("...and it carries no meta line over from the run before it", week['meta'], None)
    # The plan name is typed by hand, and it moved from a list row into a new innerHTML sink.
    pg.evaluate(HEAD, 'xss')
    pg.wait_for_timeout(200)
    check("⚠️ a hand-typed plan name in the meta line is text, not markup",
          (pg.evaluate("() => window.__xss || 0"),
           pg.evaluate("() => document.querySelectorAll('#detailMeta img').length")), (0, 0))
    check("...while it really is there, escaped",
          '&lt;img' in pg.evaluate("() => document.getElementById('detailMeta').innerHTML"), True)
    # 402 px. Not "the three numbers stay on one line": that depends on font widths, and CI's Linux
    # WebKit fonts are not his iPhone's. What must hold everywhere is that the header and the numbers
    # stay inside the panel — and a plan name this long has to wrap to do that.
    pg.set_viewport_size({"width": 402, "height": 900})
    pg.wait_for_timeout(250)
    # ⚠️ The TEXT is measured, not the meta line's box: a line that refuses to wrap spills out of its
    # own box without widening it, so a box check passed with `white-space:nowrap` (falsification,
    # 2026-09-27) — the same box-versus-ink trap as the distance tables' checks in test_goals.
    geo = pg.evaluate("""() => { DetailPanel.openSession('long');
      const r = el => el.getBoundingClientRect();
      const ink = el => { const g = document.createRange(); g.selectNodeContents(el); return g.getBoundingClientRect(); };
      const body = document.getElementById('detailBody'), meta = document.getElementById('detailMeta');
      const btn = document.getElementById('btnDetailClose');
      return { lead: document.querySelectorAll('#detailBody .dp-lead .dp-stat').length,
               wraps: r(meta).height > 30,
               fits: body.scrollWidth <= body.clientWidth && ink(meta).right <= r(btn).left
                     && r(btn).right <= r(body).right + 1,
               link: (a => a ? [a.textContent, r(a).width > 0 && r(a).right <= r(btn).left] : null)(meta.querySelector('a')) }; }""")
    check("402 px — control: a long run with a long plan name is open", (geo['lead'], geo['wraps']), (3, True))
    check("402 px — the meta line wraps short of the ✕, and nothing leaves the panel", geo['fits'], True)
    check("402 px — «Vis på Strava ↗» is there, inside the line", geo['link'], ['Vis på Strava ↗', True])
    check("no page errors in the detail header", perr, [])
    pg.close()

    # ── Older runs take their workout's name from the plan (his ask, 2026-09-29) ──────────────────
    # «All intervals are called the same regardless of regular, pyramids, broken miles» — the imported
    # plan already holds each workout's name, so one button in Planlagte økter renames the older runs,
    # locally, after a «før endring» copy. Only a run the matcher pairs with a NAMED workout (not «Easy
    # Run»); only the same workout — the same type, or Runna's record of that day's COMPLETED workout,
    # whose type is a guess from prose (a completed «Broken Miles» reads Easy); only a name that says
    # nothing of its own; never a race. Each run below is the only thing between its rule and a rename,
    # one week each, so no pairing can borrow another week's run.
    print("== older runs take their workout's name from the plan ==")
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    nerr = []
    pg.on("pageerror", lambda e: nerr.append(str(e)))
    pg.add_init_script(FREEZE)
    pg.goto(APP)
    pg.evaluate("""() => {
      const run = (id, dato, okttype, oktnavn, treningsplan = 'Runna', distanse = 6) => ({ id, dato, uke: '',
        oktnavn, okttype, treningsplan, løpetype: 'utendors', distanse, varighet: 2400, soner: [0,0,0,0,0] });
      const plan = (id, date, okttype, title, distance = 6, fromCompleted = false) =>
        ({ id, date, okttype, title, distance, fromCompleted });
      localStorage.setItem('lpl_cache', JSON.stringify({
        sessions: [
          run('L', '2026-06-14', 'Long', '', 'Runna', 14),                       // blank              → renamed
          run('K', '2026-06-17', 'Intervaller', 'Runna Intervaller'),            // nothing planned    → stays
          run('A', '2026-06-23', 'Intervaller', 'Runna Intervaller'),            // generated          → renamed
          run('B', '2026-06-30', 'Tempo', 'Runna tempo run', 'Runna', 7),        // his older spelling → renamed
          run('D', '2026-07-02', 'Easy', 'Runna Easy'),                          // «Easy Run» planned → stays
          run('C', '2026-07-05', 'Long', 'Runna Long', 'Runna', 12),             // generated          → renamed
          run('E', '2026-07-07', 'Intervaller', 'Runna intervaller'),            // completed, same day → renamed
          run('F', '2026-07-09', 'Intervaller', 'Bakkeintervaller', 'Runna', 5), // typed              → stays
          run('G', '2026-07-14', 'Easy', 'Runna Easy', 'Runna', 8),              // ran easy instead   → stays
          run('H', '2026-07-22', 'Intervaller', 'Runna Intervaller', 'Runna', 5), // completed, next day → stays
          run('I', '2026-07-25', 'Race', '', 'Runna', 10),                       // a race             → stays
          run('J', '2026-07-28', 'Intervaller', '', 'Egentrening')],             // Egentrening        → stays
        plannedSessions: [
          plan('pL', '2026-06-14', 'Long', 'Block Long Run', 14),
          plan('pA', '2026-06-23', 'Intervaller', 'Drop Set'),
          plan('pB', '2026-06-30', 'Tempo', 'Progressive Run', 7),
          plan('pD', '2026-07-02', 'Easy', 'Easy Run'),
          plan('pC', '2026-07-05', 'Long', 'Progressive Long Run', 12),
          plan('pE', '2026-07-07', 'Easy', 'Broken Miles', 6, true),
          plan('pF', '2026-07-09', 'Intervaller', '400m Repeats', 5),
          plan('pG', '2026-07-14', 'Intervaller', 'Broken Miles', 8),
          plan('pH', '2026-07-21', 'Easy', 'Drop Set', 5, true),
          plan('pI', '2026-07-25', 'Race', 'Sentrumsløpet', 10),
          plan('pJ', '2026-07-28', 'Intervaller', 'Fast 8-4-2s')],
        shoes: [], goals: {}, events: [], settings: { zones: [] }, lastUpdated: '' }));
    }""")
    pg.goto(APP)
    pg.evaluate("() => switchTab('plan')")
    pg.wait_for_timeout(400)
    BEFORE = {'L': '', 'K': 'Runna Intervaller', 'A': 'Runna Intervaller', 'B': 'Runna tempo run',
              'D': 'Runna Easy', 'C': 'Runna Long', 'E': 'Runna intervaller', 'F': 'Bakkeintervaller',
              'G': 'Runna Easy', 'H': 'Runna Intervaller', 'I': '', 'J': ''}
    RENAMED = {'L': 'Block Long Run', 'A': 'Drop Set', 'B': 'Progressive Run', 'C': 'Progressive Long Run',
               'E': 'Broken Miles'}
    NAMES = "() => Object.fromEntries(Store.data.sessions.map(s => [s.id, s.oktnavn]))"
    BTN = """() => { const b = document.getElementById('btnPlanNames');
      return b ? [getComputedStyle(b).display !== 'none', b.textContent.trim()] : 'MISSING'; }"""
    COPY = """async () => { const r = await BackupDB.restore(BackupDB.BEFORE_KEY);
      return r && [r.reason, Object.fromEntries(JSON.parse(r.json).sessions.map(s => [s.id, s.oktnavn]))]; }"""
    check("control: the fixture loaded as written", pg.evaluate(NAMES), BEFORE)
    check("the button offers the five runs", pg.evaluate(BTN), [True, 'Hent navn fra planen (5 økter)'])
    check("...and they are these five, each with its workout's name",
          pg.evaluate("() => typeof planNameRenames === 'function' ? planNameRenames().map(r => [r.s.id, r.name]) : 'MISSING'"),
          [[k, RENAMED[k]] for k in ('L', 'A', 'B', 'C', 'E')])

    dialogs = []

    def answer(accept):
        def h(d):
            dialogs.append((d.type, d.message))
            d.accept() if accept else d.dismiss()
        return h

    def click_names(accept):
        dialogs.clear()
        h = answer(accept)
        pg.on("dialog", h)
        pg.evaluate("() => document.getElementById('btnPlanNames')?.click()")
        pg.wait_for_timeout(600)
        pg.remove_listener("dialog", h)
        return list(dialogs)

    asked = click_names(False)
    msg = asked[0][1] if asked else ''
    check("the confirm names the count first", msg.split('\n')[0], 'Gi 5 økter navn fra planen?')
    check("...then every rename, oldest first, old name → new",
          [l for l in msg.split('\n') if l[:2].isdigit()],     # the dated lines — the footer has a → too
          ['14.06.2026  (uten navn) → Block Long Run', '23.06.2026  Runna Intervaller → Drop Set',
           '30.06.2026  Runna tempo run → Progressive Run', '05.07.2026  Runna Long → Progressive Long Run',
           '07.07.2026  Runna intervaller → Broken Miles'])
    check("cancel changes nothing", pg.evaluate(NAMES), BEFORE)
    check("...and takes no copy", pg.evaluate(COPY), None)

    # The copy is the only way back, so no copy means no change — the same rule as «Tøm alle data».
    pg.evaluate("""() => { window.__saveBefore = BackupDB.saveBefore;
      BackupDB.saveBefore = async () => { throw new DOMException('Disken er full', 'QuotaExceededError'); }; }""")
    asked = click_names(True)
    check("a copy that fails renames nothing", pg.evaluate(NAMES), BEFORE)
    check("...and says so", [t for t, _ in asked] == ['confirm', 'alert']
          and asked[1][1].startswith('Kunne ikke ta sikkerhetskopi — ingen navn er endret'), True)
    pg.evaluate("() => { BackupDB.saveBefore = window.__saveBefore; }")

    check("control: nothing has dated the data yet", pg.evaluate("() => Store.data.lastUpdated"), '')
    click_names(True)
    check("accepting renames exactly those five — every other name as it was",
          pg.evaluate(NAMES), {**BEFORE, **RENAMED})
    check("the «før endring» copy holds every name from before", pg.evaluate(COPY), ['Navn fra planen', BEFORE])
    check("the change is dated", pg.evaluate("() => !!Store.data.lastUpdated"), True)
    check("the toast says what happened",
          '5 økter fikk navn fra planen' in pg.evaluate("() => [...document.querySelectorAll('.toast')].map(t => t.textContent)"),
          True)
    check("the button is gone — nothing left to rename", pg.evaluate(BTN)[0], False)
    pg.goto(APP)
    pg.wait_for_timeout(500)
    check("the new names survive a reload", pg.evaluate(NAMES), {**BEFORE, **RENAMED})
    check("no page errors while renaming", nerr, [])
    pg.close()

    b.close()

print(f"\n{passed}/{passed+failed} passed" + ("" if not failed else f"  ({failed} FAILED)"))
sys.exit(1 if failed else 0)
