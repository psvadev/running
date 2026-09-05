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

    def with_events(evts):
        data = {'sessions': ramp_sessions(), 'shoes': [], 'shoeDefaults': {}, 'goals': {},
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
    check('no events → no qualifier at all', 'inneholder redusert løping' in clean, False)
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
    check('...names the baseline content', '4-ukersgrunnlaget (deload)' in both, True)
    check('...and the acute content', 'siste 7 dager (taper)' in both, True)
    # The volume card must NEVER claim a direction: it fires both ways (📈/📉), so "makes it bigger"
    # flips meaning with the sign.
    check('volum names both periods', 'begge periodene inneholder redusert løping' in both, True)
    check('...without a direction claim', 'ser større ut' in both, False)

    # An event that STARTS before a window and ends inside it still belongs to that window.
    # Start-date-only matching was the actual bug in the console probe this feature came from.
    overlap = with_events([ev('vacation', 40, 30)])
    check('an event overlapping the baseline counts', 'løfter tallet' in overlap, True)

    if errs:
        print('  PAGE ERRORS:', errs)
        failed += 1

    b.close()

print(f"\n{passed}/{passed + failed} passed" + (f"  ({failed} FAILED)" if failed else ""))
sys.exit(1 if failed else 0)
