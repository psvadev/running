"""Innsikter — the "maks puls contradicted by your own runs" card.  (2026-08-11)

Standalone — NOT part of run_all.py, which is the fast no-browser gate. Run directly:
    python tests/test_insights.py          (needs Playwright + WebKit)

Why a suite and not a port: the generator reads Store and renders DOM, and its whole point is
WHEN it fires. A port could check arithmetic; only this can check the gating.

WHAT THIS PROTECTS. The card exists because an age-estimated max HR of 183 sat in Strava for
months while three logged runs had already peaked at 195, 188 and 187 — and it was found by
accident, not by any check. Every zone boundary is a percentage of that setting, so a max that is
too low files tempo work as threshold and drags Treningsbelastning and PMC up with it.

The two gates use DIFFERENT windows on purpose, and each has a failure mode the other cannot cover:
  corroboration, ALL-TIME  — one reading is an optical-sensor spike, two is evidence. Not windowed,
                             because a hard effort every six weeks would never put two inside one.
  recency, 12 WEEKS        — at least one exceedance must be recent, so the card ages out instead of
                             nagging forever. This is what replaces a stored dismissal flag.
Every negative case below is one of those gates doing its job. If a gate is ever loosened, the
matching case here should fail FIRST — that is the whole reason they are separate scenarios rather
than one fixture.

THE CLOCK IS PINNED. "Last 12 weeks" is date arithmetic, so a fixture dated off the real today
would drift across the boundary on its own (see test_weeknow.py, which learned this the hard way).

No local data file exists (see memory reference-mobile-repro) — sessions are synthesised in-page.
"""
import json, pathlib, sys
sys.stdout.reconfigure(encoding='utf-8')   # æøå in the assertions
from playwright.sync_api import sync_playwright

APP = (pathlib.Path(__file__).resolve().parent.parent / "puls.html").as_uri()
passed = failed = 0

FAKE_TODAY = (2026, 8, 12)      # a Wednesday; nothing here depends on the weekday, only on the date

FREEZE = """
(() => {
  const R = Date;
  const fixed = new R(%d, %d, %d, 12, 0, 0).getTime();
  function F(...a) { return a.length ? new R(...a) : new R(fixed); }
  F.prototype = R.prototype; F.now = () => fixed; F.parse = R.parse; F.UTC = R.UTC;
  window.Date = F;
})();
""" % (FAKE_TODAY[0], FAKE_TODAY[1] - 1, FAKE_TODAY[2])


def check(name, got, want):
    global passed, failed
    if got == want:
        passed += 1
        print(f"  PASS {name}")
    else:
        failed += 1
        print(f"  FAIL {name}\n       got  {got!r}\n       want {want!r}")


def days_ago(n):
    import datetime
    return (datetime.date(*FAKE_TODAY) - datetime.timedelta(days=n)).isoformat()


def session(dato, toppuls, **extra):
    """A minimally complete run. Only `dato` and `toppuls` matter to the generator, but the rest of
    the dashboard renders over the same array, so keep them plausible."""
    s = {'id': f's{dato}{toppuls}', 'dato': dato, 'okttype': 'Easy', 'distanse': 6.0,
         'varighet': 2400, 'tempo': 400, 'snittkmh': 9.0, 'gjsnittspuls': 150,
         'toppuls': toppuls, 'soner': [0, 1800, 600, 0, 0], 'løpetype': 'utendors'}
    s.update(extra)
    return s


def insights_text(pg, sessions, max_hr):
    """Boot with this fixture and return the rendered Innsikter text."""
    data = {'sessions': sessions, 'shoes': [], 'shoeDefaults': {}, 'goals': {}, 'events': [],
            'plannedSessions': [], 'customSessionTypes': [], 'customPlans': [],
            'consistencySettings': {'kmThreshold': 15, 'runThreshold': 2}, 'lastUpdated': ''}
    if max_hr is not None:
        data['settings'] = {'maxHR': max_hr, 'zones': []}
    pg.goto(APP)
    pg.evaluate("d => localStorage.setItem('lpl_cache', JSON.stringify(d))", data)
    pg.goto(APP)
    pg.wait_for_timeout(500)
    pg.evaluate("() => switchTab('dash')")
    pg.wait_for_timeout(400)
    return " ".join(pg.inner_text('#insightCard').split())


FIRES = 'løp over maks puls'

with sync_playwright() as p:
    b = p.webkit.launch()
    pg = b.new_page(viewport={'width': 1280, 'height': 900})
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.add_init_script(FREEZE)

    # ── The real case: the situation that actually happened ────────────────────────────────────
    print("== fires on corroborated, recent evidence ==")
    txt = insights_text(pg, [
        session(days_ago(200), 188),      # old evidence still counts toward corroboration
        session(days_ago(10), 195),       # recent, and the peak
        session(days_ago(3), 150),        # ordinary run, under the setting
    ], 183)
    check('card fires', FIRES in txt, True)
    check('counts BOTH exceedances', '2 løp over maks puls' in txt, True)
    check('names the peak, not the latest', '195 bpm' in txt, True)
    check('names the setting it contradicts', 'mot 183 satt' in txt, True)
    # The generator is wrapped in a try/catch that prints DEBUG on throw — a card that renders an
    # exception message still "contains" nothing we assert on, so check the catch never fired.
    check('no generator exception', 'DEBUG' in txt, False)

    # ── Gate 1: corroboration. A single spike must never fire ──────────────────────────────────
    print("== one reading is not evidence ==")
    txt = insights_text(pg, [
        session(days_ago(10), 199),       # a lone optical-sensor spike
        session(days_ago(3), 150),
    ], 183)
    check('single exceedance stays silent', FIRES in txt, False)

    # ── Gate 2: recency. Old evidence must age out rather than nag forever ─────────────────────
    print("== stale evidence ages out ==")
    txt = insights_text(pg, [
        session(days_ago(200), 195),
        session(days_ago(120), 188),      # both older than the 12-week window
        session(days_ago(3), 150),
    ], 183)
    check('nothing recent stays silent', FIRES in txt, False)
    # ...and the boundary itself: 84 days is inside, 85 is not.
    txt = insights_text(pg, [session(days_ago(200), 195), session(days_ago(84), 188)], 183)
    check('day 84 is inside the window', FIRES in txt, True)
    txt = insights_text(pg, [session(days_ago(200), 195), session(days_ago(85), 188)], 183)
    check('day 85 is outside it', FIRES in txt, False)

    # ── Materiality: grazing the limit says nothing ────────────────────────────────────────────
    print("== a graze is not an error ==")
    txt = insights_text(pg, [
        session(days_ago(200), 184),
        session(days_ago(10), 185),       # peak is only +2
    ], 183)
    check('+2 bpm stays silent', FIRES in txt, False)
    txt = insights_text(pg, [session(days_ago(200), 184), session(days_ago(10), 186)], 183)
    check('+3 bpm fires', FIRES in txt, True)

    # ── Avvik: a run flagged for a faulty strap must not drive it ──────────────────────────────
    # This is exactly what the flag is for, and the generator reads qualitySessions to get it.
    print("== flagged outliers cannot drive it ==")
    txt = insights_text(pg, [
        session(days_ago(200), 195, utenforAnalyse=True),
        session(days_ago(10), 188, utenforAnalyse=True),
    ], 183)
    check('Avvik-flagged exceedances ignored', FIRES in txt, False)
    # One flagged, one not → back to a single valid reading, so still silent. Proves the filter
    # runs BEFORE the count rather than after it.
    txt = insights_text(pg, [
        session(days_ago(200), 195, utenforAnalyse=True),
        session(days_ago(10), 188),
    ], 183)
    check('filter applies before the count', FIRES in txt, False)

    # ── No setting, no claim ───────────────────────────────────────────────────────────────────
    print("== silent without a configured max ==")
    txt = insights_text(pg, [session(days_ago(200), 195), session(days_ago(10), 188)], None)
    check('unset maxHR stays silent', FIRES in txt, False)

    # ── The card must disappear once acted on. This is the anti-clutter property that earned it
    # a place: raising the setting past the evidence silences it with no state to store.
    print("== acting on it silences it ==")
    fixture = [session(days_ago(200), 195), session(days_ago(10), 188)]
    check('fires at 183', FIRES in insights_text(pg, fixture, 183), True)
    check('silent at 195 after the fix', FIRES in insights_text(pg, fixture, 195), False)

    # ── Low-load qualifier on Belastning + volum  (2026-09-05) ─────────────────────────────────
    # ⚠️ Uses days_ago(), i.e. FAKE_TODAY — the suite freezes window.Date via add_init_script, so
    # the app's localISODate() is 2026-08-12 regardless of the real clock. Building these fixtures
    # off datetime.date.today() instead puts every event on the wrong side of the ACWR and volume
    # windows, and the cards still render, just with the wrong qualifier. That failure is silent:
    # the cards fire, the control passes, and only the wording is wrong.

    def ramp_sessions():
        """A genuine ramp: last 4 weeks heavier than the prior 4, last 7 days heavier still, so
        BOTH the volume card and the ACWR card clear their thresholds."""
        out = []
        for i, n in enumerate(range(56, -1, -2)):
            if n <= 7:      zones, dur, km = [0, 300, 900, 1500, 600], 3300, 14
            elif n < 28:    zones, dur, km = [0, 600, 1200, 600, 0], 2400, 11
            else:           zones, dur, km = [0, 600, 600, 300, 0], 1500, 6
            out.append({'id': f'r{i}', 'dato': days_ago(n), 'okttype': 'Easy', 'distanse': km,
                        'varighet': dur, 'tempo': 360, 'snittkmh': 10.0, 'gjsnittspuls': 150,
                        'toppuls': 170, 'soner': zones, 'løpetype': 'utendors',
                        'treningsplan': 'Runna'})
        return out

    def with_events(evts, extra=()):
        data = {'sessions': ramp_sessions() + list(extra), 'shoes': [], 'shoeDefaults': {}, 'goals': {},
                'events': evts, 'plannedSessions': [], 'customSessionTypes': [], 'customPlans': [],
                'consistencySettings': {'kmThreshold': 15, 'runThreshold': 2},
                'settings': {'maxHR': 195, 'zones': []}, 'lastUpdated': ''}
        pg.goto(APP)
        pg.evaluate("d => localStorage.setItem('lpl_cache', JSON.stringify(d))", data)
        pg.goto(APP)
        pg.wait_for_timeout(500)
        pg.evaluate("() => switchTab('dash')")
        pg.wait_for_timeout(400)
        return " ".join(pg.inner_text('#insightCard').split())

    def ev(kind, frm, to):
        return {'id': f'{kind}{frm}', 'type': kind, 'title': kind,
                'date': days_ago(frm), 'endDate': days_ago(to)}

    def card_with(marker):
        """Text of the ONE .insight-item containing `marker`.

        ⚠️ Wording assertions must be scoped to their own card. The two qualifiers share vocabulary
        — the volume card's "(deload/taper nå, ferie før)" contains the literal 'taper nå' — so a
        check about the BELASTNING card that searches the whole panel is satisfied by the VOLUME
        card and can never fail. Found by falsification: swapping the ACWR pairing to "deload nå,
        taper før" left 'taper nå' green. Reads textContent, not innerText, per the off-DOM rule.
        Returns '' when no card matches, so a True-expecting check fails loudly rather than passing.
        """
        for t in pg.eval_on_selector_all('.insight-item', "els => els.map(e => e.textContent)"):
            t = " ".join(t.split())
            if marker in t:
                return t
        return ''

    print('== low-load qualifier ==')
    clean = with_events([])
    # ⚠️ POSITIVE CONTROL FIRST. Every assertion below is about the WORDING of two cards; if the
    # fixture stopped making them fire, they would all read "phrase absent" and pass as though the
    # feature worked. This is the only line that proves there is anything to inspect.
    check('control: both cards fire on a clean ramp',
          ('Belastning ×' in clean) and ('mer volum' in clean), True)
    check('the risk claim is gone', 'skaderisiko' in clean, False)
    check('...replaced by what was measured', 'stor belastningsøkning' in clean, True)
    check('the instruction survives', 'ro ned' in clean, True)
    # 'redusert løping' is the stem every qualifier variant shares, in both cards and all three
    # window cases — so its absence is the honest "no qualifier at all". (It used to pin
    # 'inneholder redusert løping'; the 2026-09-05 reword dropped the verb, which would have left
    # this check passing because the phrase no longer exists ANYWHERE. Restated, not loosened.)
    check('no events → no qualifier at all', 'redusert løping' in clean, False)
    check('...and no direction claim either', 'løfter tallet' in clean, False)

    # Deload in the ACWR baseline (days 8-35) only — direction is knowable, so it is stated.
    base_only = with_events([ev('deload', 26, 20)])
    check('deload in the baseline alone → direction stated', 'løfter tallet' in base_only, True)

    # Taper inside the acute 7 days only — it suppresses the numerator, so a high ratio despite it
    # is the interesting reading, and the wording has to say so rather than blame the baseline.
    acute_only = with_events([ev('taper', 5, 0)])
    check('taper in the acute window alone → different direction',
          'høyt likevel' in acute_only, True)
    check('...and it does NOT claim the baseline lifted it', 'løfter tallet' in acute_only, False)

    # Both windows affected — his real 2026-09-05 layout. They push opposite ways by an unknown
    # amount, so naming a direction would be a guess; the card names what is where instead.
    both = with_events([ev('deload', 26, 20), ev('taper', 5, 0), ev('vacation', 54, 48)])
    check('both windows → no direction claim', 'løfter tallet' in both, False)
    # The label must stay ATTACHED to its window, and be read off the card that owns it.
    acwr_card, vol_card = card_with('Belastning ×'), card_with('mer volum')
    check('control: both cards located individually',
          bool(acwr_card) and bool(vol_card), True)
    check('...names the baseline content', 'deload før' in acwr_card, True)
    check('...and the acute content', 'taper nå' in acwr_card, True)
    # The volume card must NEVER claim a direction: it fires both ways (📈/📉), so "makes it bigger"
    # flips meaning with the sign.
    check('volum names both periods', 'redusert løping i begge periodene' in vol_card, True)
    check('...and attaches each label to its own period',
          'deload/taper nå, ferie før' in vol_card, True)
    check('...without a direction claim', 'ser større ut' in both, False)

    # An event that STARTS before a window and ends inside it still belongs to that window.
    # Start-date-only matching was the actual bug in the console probe this feature came from.
    overlap = with_events([ev('vacation', 40, 30)])
    check('an event overlapping the baseline counts', 'løfter tallet' in overlap, True)

    # ── Race day: the card retires when the effort is logged (2026-09-11) ──────────────────────
    #
    # It used to wish you luck for a race already in the log, and at priority 5 — the highest — so
    # it held one of six slots until midnight on the day most candidates compete for them.
    #
    # ⚠️ Every pair below changes exactly ONE field. The card list is capped at six, so a fixture
    # with one more session could drop "lykke til" for crowding rather than for the guard, and the
    # check would pass for the wrong reason. Same session count, same distances, one okttype apart.
    print("== race day: the card retires once the effort is logged ==")
    TODAY = days_ago(0)

    def race(title, date):
        return {'id': 'rc' + title, 'type': 'race', 'title': title, 'date': date, 'distanceKm': 5}

    def effort(okttype):
        """Today's run. Deliberately unremarkable — slow enough to set no PR and a peak well under
        the 195 maxHR — so it cannot push cards off the row and fake a pass."""
        return {'id': 'eff', 'dato': TODAY, 'okttype': okttype, 'distanse': 5.0, 'varighet': 2400,
                'tempo': 480, 'snittkmh': 7.5, 'gjsnittspuls': 150, 'toppuls': 170,
                'soner': [0, 1800, 600, 0, 0], 'løpetype': 'tredemolle'}

    TEST_5K = [race('Runna 5K test', TODAY)]
    # The control, and the reason the guard is EFFORT_TYPES rather than "any session today":
    # an easy run in the morning must not retire the card for a race in the evening.
    before = with_events(TEST_5K, extra=[effort('Easy')])
    check('race day, only an easy run logged → still wished luck', 'lykke til' in before, True)
    check('...and it names the race', 'Runna 5K test' in before, True)

    for done_as in ('Test', 'Race'):
        after = with_events(TEST_5K, extra=[effort(done_as)])
        check(f'logged as {done_as} → the card is gone', 'lykke til' in after, False)

    # A future race must not be retired by today's run — only today's race can have been run.
    SOON = [race('Oslo 10K', days_ago(-10))]
    ahead = with_events(SOON, extra=[effort('Test')])
    check('a future race still counts down', 'Oslo 10K' in ahead, True)

    # The payoff for filtering the list instead of special-casing the daysUntil === 0 branch: a
    # finished race hands the slot to the NEXT race rather than taking it down with it.
    handover = with_events(TEST_5K + SOON, extra=[effort('Test')])
    check('a finished race hands over to the next', 'Oslo 10K' in handover, True)
    check('...and stops wishing luck for the finished one', 'lykke til' in handover, False)

    # ── The PR floor: only a distance you could race earns a headline (2026-09-11) ─────────────
    #
    # His 27:03 5K set THREE PRs at once — 400 m, 1 km and 5 km inne — because the analyser extracts
    # best efforts from inside a longer run. Each took its own priority-5 slot, so one session held
    # half the card and displaced everything at priority 4 and below. The floor is `r.km >= 5`.
    #
    # ⚠️ THE VACUITY TRAP, and it is the whole reason for the card-count control below. The card is
    # capped at six. A fixture with enough candidates makes "400 m is absent" pass because 400 m was
    # CROWDED OUT, not because the floor excluded it — and the check would then survive the floor
    # being deleted. The fixture is kept deliberately thin (three recent runs, low total km, nothing
    # in the 8-35 day baseline) so no other generator fires, and the control asserts the card is not
    # full. Absence in a card with free slots can only be the floor.
    print("== PR insight: floored at 5 km ==")

    def prs(top3, sessions=None):
        """Boot with a bestEffortsTop3 map and return (panel text, number of cards)."""
        runs = sessions if sessions is not None else [
            session(days_ago(n), 150, distanse=6.0) for n in (0, 2, 4)]
        data = {'sessions': runs, 'shoes': [], 'shoeDefaults': {}, 'goals': {}, 'events': [],
                'plannedSessions': [], 'customSessionTypes': [], 'customPlans': [],
                'bestEffortsTop3': top3,
                'consistencySettings': {'kmThreshold': 15, 'runThreshold': 2},
                'settings': {'maxHR': 195, 'zones': []}, 'lastUpdated': ''}
        pg.goto(APP)
        pg.evaluate("d => localStorage.setItem('lpl_cache', JSON.stringify(d))", data)
        pg.goto(APP)
        pg.wait_for_timeout(500)
        pg.evaluate("() => switchTab('dash')")
        pg.wait_for_timeout(400)
        # ⚠️ SCOPED to #insightCard. A bare '.insight-item' also matches the four stats in the
        # "Denne uken" strip, which reuses the class — counting those made the card look full
        # (8 items) when Innsikter held four, and the control below would have failed forever
        # for a reason that had nothing to do with the floor.
        n = len(pg.query_selector_all('#insightCard .insight-item'))
        return " ".join(pg.inner_text('#insightCard').split()), n

    FRESH = days_ago(2)
    # Every distance fresh on the same day, exactly like a test race that sets a cascade of them.
    # `half` is in here for a reason — see the floor-not-whitelist check below.
    txt, ncards = prs({'400m': [{'t': 100, 'd': FRESH}], '1k': [{'t': 282, 'd': FRESH}],
                       '5k': [{'t': 1623, 'd': FRESH}], '10k': [{'t': 3705, 'd': FRESH}],
                       'half': [{'t': 8100, 'd': FRESH}]})
    # POSITIVE CONTROL FIRST: without this, every "absent" check below could be reading an empty card.
    check('control: the 5 km PR fires', 'Ny 5 km-PR' in txt, True)
    check('control: the 10 km PR fires', 'Ny 10 km-PR' in txt, True)
    # THE control that makes the two absences mean something.
    check('control: card is NOT full, so absence cannot be crowding', ncards < 6, True)
    check('400 m does not take a slot', '400 m-PR' in txt, False)
    check('1 km does not take a slot', '1 km-PR' in txt, False)
    # A floor, not a hand-written whitelist of {5k, 10k}: mutating the guard to an equality test
    # against those two keys must fail here.
    check('everything above the floor still fires', 'Halvmaraton-PR' in txt, True)
    # The floor must not have quietly replaced the 14-day recency gate.
    stale, _ = prs({'5k': [{'t': 1623, 'd': days_ago(15)}]})
    check('a 15-day-old 5 km PR still ages out', 'Ny 5 km-PR' in stale, False)

    # ── A training block about to start (2026-09-11) ───────────────────────────────────────────
    #
    # ⚠️ This section also pins a LINE ORDER, and that is not obvious from reading it. The generator
    # reads `cachedBlocks`, which renderDashboard used to fill AFTER renderInsights ran — so on a
    # fresh page (which is exactly what every fixture here boots) it was `[]` and the card could
    # never appear at all. Move the assignment back below renderInsights and the first check fails.
    print("== a training block about to start ==")

    def blocks(plan_evts):
        data = {'sessions': [session(days_ago(n), 150, distanse=6.0) for n in (0, 2, 4)],
                'shoes': [], 'shoeDefaults': {}, 'goals': {}, 'events': plan_evts,
                'plannedSessions': [], 'customSessionTypes': [], 'customPlans': [],
                'consistencySettings': {'kmThreshold': 15, 'runThreshold': 2},
                'settings': {'maxHR': 195, 'zones': []}, 'lastUpdated': ''}
        pg.goto(APP)
        pg.evaluate("d => localStorage.setItem('lpl_cache', JSON.stringify(d))", data)
        pg.goto(APP)
        pg.wait_for_timeout(500)
        pg.evaluate("() => switchTab('dash')")
        pg.wait_for_timeout(400)
        return " ".join(pg.inner_text('#insightCard').split())

    def plan(title, starts_in, weeks=12, **extra):
        e = {'id': 'pl' + title, 'type': 'plan', 'title': title,
             'date': days_ago(-starts_in), 'endDate': days_ago(-starts_in - weeks * 7)}
        e.update(extra)
        return e

    soon = blocks([plan('Runna 10K #2', 3, targetTotalKm=300)])
    check('a block 3 days out counts down', '3 dager' in soon, True)
    check('...and names the block', 'til Runna 10K #2 starter' in soon, True)
    check('...and carries its span', '12 uker' in soon, True)
    check('...and its target when set', 'mål 300 km' in soon, True)
    check('singular on the last day', '1 dag ' in blocks([plan('Runna 10K #2', 1)]), True)

    # Gating: 14 days, the same shape as the race countdown's 30. A block further out is trivia,
    # and the Treningsblokker card carries it from any distance anyway.
    check('day 14 is inside the window',
          'starter' in blocks([plan('Runna 10K #2', 14)]), True)
    check('day 15 is outside it',
          'starter' in blocks([plan('Runna 10K #2', 15)]), False)

    # It retires BY CONSTRUCTION: once started, the block is `current` and no longer matches the
    # filter. This is the check that would catch someone "fixing" it with a daysUntil === 0 branch —
    # the exact bug shape the race card had until today.
    # Carries a target so the plan-progress card can fire — that card is the control below, and
    # `activePlan` ignores a plan with neither targetTotalKm nor targetKmPerWeek set.
    started = blocks([plan('Runna 10K #2', -2, targetTotalKm=300)])
    check('a block already underway does not count down', 'starter' in started, False)
    # ...and the control proving that fixture reaches the generator at all, so the line above is not
    # passing because nothing rendered.
    check('control: the started block still drives plan progress',
          'Runna 10K #2' in started, True)

    # ── ...and it has to survive a card that is already FULL ───────────────────────────────────
    #
    # ⚠️ THIS IS THE CHECK THE SECTION ABOVE COULD NOT MAKE, and the bug is the proof. Every fixture
    # above is deliberately thin, so the countdown had no competition and "it appears" passed at a
    # flat priority 4. On his real dashboard the same code rendered NOTHING: four cards at priority
    # 5 (a km milestone + three fresh PRs) took the top, and two OTHER priority-4 cards — maks puls
    # and the volume trend — were pushed to `candidates` earlier, so a stable sort left the
    # countdown seventh of six. A presence test on an empty card proves a generator RUNS; only a
    # contested card proves it EARNS a slot.
    #
    # The fixture reproduces that pile-up: a km milestone + 3 PRs at priority 5, maks puls and a
    # >25 % volume jump at priority 4, and a block 3 days out. Sessions are Steady with no zone data
    # on purpose, so the Easy-trend, Zone-2, ACWR and fastest-Easy generators stay silent and the
    # competition is only the cards this check is about.
    print("== the countdown survives a full card ==")

    crowd = ([session(days_ago(n), 150, okttype='Steady', distanse=6.0, tempo=0,
                      soner=[0, 0, 0, 0, 0]) for n in range(29, 56, 3)]             # prior 4wk: 54 km
             + [session(days_ago(n), 201 if n in (3, 6) else 150, okttype='Steady', distanse=7.0,
                        tempo=0, soner=[0, 0, 0, 0, 0]) for n in range(0, 28, 3)])  # recent: 70 km
    data = {'sessions': crowd, 'shoes': [], 'shoeDefaults': {}, 'goals': {},
            'events': [plan('Runna 10K #2', 3, targetTotalKm=300)],
            'plannedSessions': [], 'customSessionTypes': [], 'customPlans': [],
            'bestEffortsTop3': {'5k': [{'t': 1623, 'd': FRESH}], '10k': [{'t': 3705, 'd': FRESH}],
                                'half': [{'t': 8100, 'd': FRESH}]},
            'consistencySettings': {'kmThreshold': 15, 'runThreshold': 2},
            'settings': {'maxHR': 195, 'zones': []}, 'lastUpdated': ''}
    pg.goto(APP)
    pg.evaluate("d => localStorage.setItem('lpl_cache', JSON.stringify(d))", data)
    pg.goto(APP)
    pg.wait_for_timeout(500)
    pg.evaluate("() => switchTab('dash')")
    pg.wait_for_timeout(400)
    full = " ".join(pg.inner_text('#insightCard').split())
    nfull = len(pg.query_selector_all('#insightCard .insight-item'))

    # Controls FIRST: without them "the countdown is present" could be passing on a card with
    # nothing else on it, which is the very hole this section exists to close.
    check('control: the card is genuinely full', nfull, 6)
    check('control: a km milestone holds a slot', 'totalt passert' in full, True)
    check('control: the PRs hold slots', full.count('-PR') >= 3, True)
    check('control: another priority-4 card is competing', 'over maks puls' in full, True)
    check('the block countdown still earns a slot', 'starter' in full, True)

    if errs:
        print('  PAGE ERRORS:', errs)
        failed += 1

    b.close()

print(f"\n{passed}/{passed + failed} passed" + (f"  ({failed} FAILED)" if failed else ""))
sys.exit(1 if failed else 0)
