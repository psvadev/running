"""Strava-gated controls: disabled + an inline reason when disconnected, live when connected. (2026-08-13)

Standalone — NOT part of run_all.py. Run directly:
    python tests/test_strava_gating.py      (needs Playwright + WebKit)

WHY THIS SUITE EXISTS: this behaviour is invisible to the app's only user. His Strava is permanently
connected, so the disconnected state is one he will never see and can never report a regression in.
Unobservable + untested is the definition of something that rots silently, which is the whole reason
the gating was inconsistent in the first place — one precondition answered three different ways
(hidden / disabled / looks-live-then-complains-on-click).

Two properties that are easy to break and cost nothing to assert:
  * the reason is TEXT beside the button, not a title tooltip — a phone has no hover, so a dimmed
    button with a tooltip-only explanation is a dead end there;
  * a re-render must not clobber a live sync progress message sharing the same span.

Not connected is the default state of a fresh profile, so the disconnected half needs no setup.
The connected half fakes a stored token — StravaIO.isSignedIn() only checks for a refresh_token.
"""
import pathlib, sys
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

# Relative to this file, not the repo checkout path — CI clones somewhere else entirely.
APP = (pathlib.Path(__file__).resolve().parent.parent / "puls.html").as_uri()
HINT = 'Koble til Strava i Innstillinger først'
passed = failed = 0


def check(name, got, want):
    global passed, failed
    if got == want:
        passed += 1; print(f"  PASS {name}")
    else:
        failed += 1; print(f"  FAIL {name}\n       got  {got!r}\n       want {want!r}")


STATE = """() => {
  const b = id => { const e = document.getElementById(id); return e ? e.disabled : 'MISSING'; };
  const t = id => { const e = document.getElementById(id); return e ? e.textContent.trim() : 'MISSING'; };
  const shown = id => { const e = document.getElementById(id);
                        return e ? getComputedStyle(e).display !== 'none' : 'MISSING'; };
  return { syncDisabled: b('btnSyncBestEfforts'), zonesDisabled: b('btnStravaZones'),
           syncMsg: t('bestEffortsSyncMsg'), zonesMsg: t('stravaZonesMsg'),
           rescanShown: shown('btnForceRescanBE'),
           syncOpacity: getComputedStyle(document.getElementById('btnSyncBestEfforts')).opacity };
}"""

with sync_playwright() as p:
    b = p.webkit.launch()
    pg = b.new_page()
    pg.goto(APP)
    pg.evaluate("() => switchTab('settings')")
    pg.wait_for_timeout(400)

    print("== not connected ==")
    s = pg.evaluate(STATE)
    check("sync button disabled", s["syncDisabled"], True)
    check("zones button disabled", s["zonesDisabled"], True)
    check("...and visibly dimmed", s["syncOpacity"], "0.45")
    check("sync reason shown inline", s["syncMsg"], HINT)
    check("zones reason shown inline", s["zonesMsg"], HINT)
    check("rescan link hidden", s["rescanShown"], False)

    print("== connected ==")
    pg.evaluate("""() => {
      localStorage.setItem('pulsStravaToken', JSON.stringify(
        { refresh_token:'x', access_token:'y', expires_at: Date.now()/1000 + 9999 }));
      Settings.render();
    }""")
    pg.wait_for_timeout(300)
    s = pg.evaluate(STATE)
    check("sync button live", s["syncDisabled"], False)
    check("zones button live", s["zonesDisabled"], False)
    check("...and undimmed", s["syncOpacity"], "1")
    check("sync hint cleared", s["syncMsg"], "")
    check("zones hint cleared", s["zonesMsg"], "")
    check("rescan link shown", s["rescanShown"], True)

    print("== a live progress message survives a re-render ==")
    pg.evaluate("""() => {
      document.getElementById('bestEffortsSyncMsg').textContent = 'Skanner … 340 aktiviteter';
      Settings.render();
    }""")
    pg.wait_for_timeout(200)
    check("progress text not clobbered",
          pg.evaluate("() => document.getElementById('bestEffortsSyncMsg').textContent"),
          'Skanner … 340 aktiviteter')

    print("== 402px: the hint does not overflow the card ==")
    pg.close()
    pg = b.new_page(viewport={"width": 402, "height": 850})
    pg.goto(APP)
    pg.evaluate("() => switchTab('settings')")
    pg.wait_for_timeout(400)
    check("page does not scroll sideways", pg.evaluate(
        "() => document.body.scrollWidth <= document.documentElement.clientWidth + 1"), True)
    pg.close()

    # ── HR graph in the session detail (2026-09-22) ─────────────────────────────────────────
    # Fetched when a run is OPENED, never stored — his call. So the failure states are the whole
    # feature's surface: not connected, no link, offline, rate-limited, no HR. He will almost never
    # see any of them, which is exactly why they are asserted here rather than trusted.
    print("== HR graph: fetched on open, never stored ==")
    ZONES = "[{min:98,max:117},{min:117,max:137},{min:137,max:156},{min:156,max:176},{min:176,max:195}]"
    HR_SEED = """() => localStorage.setItem('lpl_cache', JSON.stringify({ sessions: [
      {id:'out', dato:'2026-09-19', uke:'2026-38', oktnavn:'Long Run', okttype:'Long', treningsplan:'Runna',
       løpetype:'utendors', distanse:17, varighet:7440, soner:[420,2460,4080,480,0], stravaId:'111'},
      {id:'tm',  dato:'2026-09-16', uke:'2026-38', oktnavn:'6 x 800 m', okttype:'Intervaller', treningsplan:'Runna',
       løpetype:'treadmill', distanse:7.2, varighet:3000, soner:[360,900,780,660,300], stravaId:'222'},
      {id:'man', dato:'2026-09-12', uke:'2026-37', oktnavn:'Tur', okttype:'Easy', treningsplan:'Egentrening',
       løpetype:'utendors', distanse:5, varighet:1800, soner:[0,1800,0,0,0]}],
      shoes:[], goals:{}, events:[], plannedSessions:[], settings:{ maxHR:195, zones:""" + ZONES + """ },
      lastUpdated:'' }))"""
    TOKEN = """() => localStorage.setItem('pulsStravaToken', JSON.stringify(
        { refresh_token:'x', access_token:'y', expires_at: Date.now()/1000 + 9999 }))"""
    # 1 Hz synthetic stream, with a 90 s stop at 40 min so the pace gap is testable.
    STUB = """(mode) => {
      const mk = () => { const time=[], hr=[], vel=[], moving=[];
        for (let s = 0; s <= 3600; s++) { const stop = s >= 2400 && s < 2490;
          time.push(s); hr.push(130 + Math.round(10 * Math.sin(s / 300))); vel.push(stop ? 0 : 2.3); moving.push(!stop); }
        return { time:{data:time}, heartrate:{data:hr}, velocity_smooth:{data:vel}, moving:{data:moving} }; };
      window.__calls = 0; window.__holds = [];
      StravaIO.fetchActivityStreams = async (id) => { window.__calls++;
        if (mode === 'hold') await new Promise(r => { window.__holds.push(r); });
        if (mode === '429') return { error: 429 };
        if (mode === 'offline') return null;
        if (mode === 'nohr') { const d = mk(); delete d.heartrate; return d; }
        return mk(); };
    }"""

    def fresh(token=True, pace=None):
        pg = b.new_page(viewport={"width": 900, "height": 1200})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(APP)
        pg.evaluate(HR_SEED)
        if token:
            pg.evaluate(TOKEN)
        if pace is not None:
            pg.evaluate(f"() => localStorage.setItem('lpl_hr_pace', '{pace}')")
        pg.goto(APP)
        pg.wait_for_timeout(500)
        return pg, errs

    def open_run(pg, sid, wait=400):
        pg.evaluate(f"() => DetailPanel.openSession('{sid}')")
        pg.wait_for_timeout(wait)

    slot = "() => { const e = document.getElementById('hrGraph'); return e ? e.innerText.trim() : null; }"
    canvases = "() => document.querySelectorAll('#hrGraph canvas').length"

    pg, errs = fresh(token=False)
    pg.evaluate(STUB, "ok")
    open_run(pg, "out")
    check("not connected: says so in text, rather than an empty space",
          "koble til Strava" in pg.inner_text("#detailBody"), True)
    check("...and asks Strava for nothing", pg.evaluate("() => window.__calls"), 0)
    pg.close()

    pg, errs = fresh()
    pg.evaluate(STUB, "ok")
    open_run(pg, "man")
    check("a run with no Strava link gets no graph at all", pg.evaluate(slot), None)
    check("...and no fetch", pg.evaluate("() => window.__calls"), 0)

    before = pg.evaluate("() => JSON.stringify(Store.data)")
    open_run(pg, "out")
    check("a linked run draws the graph", pg.evaluate(canvases), 1)
    check("...from exactly one fetch", pg.evaluate("() => window.__calls"), 1)
    check("⚠️ ...and writes NOTHING to the store — fetched, never kept",
          pg.evaluate("() => JSON.stringify(Store.data)"), before)
    check("pace is OFF by default", pg.evaluate("() => !!document.getElementById('hrGraphPace')"), False)
    check("...with the toggle offered on an outdoor run",
          pg.evaluate("() => !!document.getElementById('hrPaceToggle')"), True)
    # A lone unfilled pill read as a LABEL on his screen. The pair, with one lit, is what says switch.
    check("⚠️ the toggle is a PAIR with the current state lit",
          pg.evaluate("""() => [document.getElementById('hrPaceOff')?.classList.contains('active'),
                                document.getElementById('hrPaceToggle')?.classList.contains('active')]"""),
          [True, False])
    check("...sitting ABOVE the chart, where the dashboard puts its toggles", pg.evaluate("""() =>
        document.getElementById('hrPaceToggle').getBoundingClientRect().bottom
        <= document.getElementById('hrGraphHr').getBoundingClientRect().top"""), True)

    pg.click("#hrPaceToggle")
    pg.wait_for_timeout(250)
    check("the toggle adds the pace strip", pg.evaluate("() => !!document.getElementById('hrGraphPace')"), True)
    check("...without a second fetch", pg.evaluate("() => window.__calls"), 1)
    check("...and remembers the choice", pg.evaluate("() => localStorage.getItem('lpl_hr_pace')"), "1")
    pg.click("#hrPaceToggle")
    pg.wait_for_timeout(200)
    check("clicking the lit pill again is a no-op, not a flip back",
          pg.evaluate("() => !!document.getElementById('hrGraphPace')"), True)

    # Chart.js keeps an instance alive after its canvas is removed from the page, so a panel that
    # replaces the body without destroy() leaks one chart per run opened.
    live_hr = """() => Object.values(Chart.instances || {})
        .filter(c => (c.canvas?.id || '').startsWith('hrGraph')).length"""
    check("two HR charts are live while the graph is shown", pg.evaluate(live_hr), 2)
    open_run(pg, "man")
    check("...and none once the panel shows another run", pg.evaluate(live_hr), 0)
    open_run(pg, "out")
    check("reopening the run in the same visit re-uses what was fetched",
          pg.evaluate("() => window.__calls"), 1)
    check("...and opens with pace on, as left", pg.evaluate("() => !!document.getElementById('hrGraphPace')"), True)
    # A stop is a GAP, not a straight line drawn through the stop at the average of either side.
    check("a stop leaves a gap in the pace series", pg.evaluate("""() => {
        const s = hrGraphSeries({ time:{data:[...Array(600).keys()]}, heartrate:{data:Array(600).fill(140)},
          velocity_smooth:{data:[...Array(600)].map((_, i) => i >= 300 && i < 360 ? 0 : 2.5)} });
        return s.pace.some(p => p == null) && s.pace.some(p => p != null); }"""), True)

    open_run(pg, "tm")
    check("a treadmill run offers no pace toggle", pg.evaluate("() => !!document.getElementById('hrPaceToggle')"), False)
    check("...even with pace switched on", pg.evaluate("() => !!document.getElementById('hrGraphPace')"), False)
    check("...and says why", "innendørstempo" in (pg.evaluate(slot) or ""), True)
    # ⚠️ The caption used to blame the treadmill for THREE different causes, because `!series.pace` is
    # all it had: an indoor run, a missing velocity stream, and a run that never left walking speed.
    # An OUTDOOR run whose stream Strava has no speed for was therefore told it was on a treadmill.
    check("the series says WHY there is no pace, not just that there is none",
          pg.evaluate("""() => { const t = [...Array(600).keys()], hr = t.map(() => 140);
            const tm = hrGraphSeries({ time:{data:t}, heartrate:{data:hr} }, { treadmill: true });
            const out = hrGraphSeries({ time:{data:t}, heartrate:{data:hr} });
            return [tm.paceOff, out.paceOff]; }"""), ["treadmill", "none"])
    pg.close()
    # ...and on screen: same missing pace, different sentence.
    pg, errs = fresh()
    pg.evaluate("""() => { StravaIO.fetchActivityStreams = async () => { const t = [...Array(600).keys()];
        return { time:{data:t}, heartrate:{data:t.map(() => 140)} }; }; }""")   # outdoor, no velocity
    open_run(pg, "out")
    cap = pg.evaluate(slot) or ""
    check("an outdoor run with no speed data is not called a treadmill", "Tredemølle" in cap, False)
    check("...it says Strava has no pace for it", "ikke tempodata" in cap, True)
    check("no HR-graph page errors", errs, [])
    pg.close()

    # Each failure must NAME itself. "Nothing drawn" means five different things here.
    for mode, want in [("offline", "er du på nett"), ("429", "for mange forespørsler"),
                       ("nohr", "ingen pulsdata")]:
        pg, errs = fresh()
        pg.evaluate(STUB, mode)
        open_run(pg, "out")
        check(f"{mode}: says so in one line", want in (pg.evaluate(slot) or ""), True)
        check(f"{mode}: ...draws no chart", pg.evaluate(canvases), 0)
        pg.close()

    # Retry semantics: a network failure is worth another try; "no HR" is not going to change.
    pg, errs = fresh()
    pg.evaluate(STUB, "offline")
    open_run(pg, "out")
    open_run(pg, "man")
    open_run(pg, "out")
    check("an offline failure is retried on the next open", pg.evaluate("() => window.__calls"), 2)
    pg.close()

    # ⚠️ The race. Open A, then B before A's fetch returns: A's answer must not land in B's panel.
    pg, errs = fresh()
    pg.evaluate(STUB, "hold")
    open_run(pg, "out", wait=150)
    open_run(pg, "tm", wait=150)
    # Release A's fetch ONLY — one resolver per call. A single shared resolver would be overwritten
    # by B's and release B instead, which then draws its own graph and proves nothing (this test's
    # first draft did exactly that). And the slot's id is B's regardless, so the proof is that no
    # chart appeared in it.
    pg.evaluate("() => window.__holds[0]()")
    pg.wait_for_timeout(300)
    check("⚠️ a slow fetch for one run never draws into another run's panel",
          pg.evaluate(canvases), 0)
    check("...and B's own slot is left loading, not overwritten by A",
          "Henter puls" in (pg.evaluate(slot) or ""), True)
    pg.evaluate("() => window.__holds[1]()")
    pg.wait_for_timeout(300)
    check("...until B's own answer arrives and draws", pg.evaluate(canvases), 1)
    pg.close()

    # ⚠️ Zones as HE stores them, not as a tidy fixture would. The first build demanded all ten
    # boundaries, his Sone 1 floor is `null`, and so the bands silently vanished on his real data
    # while every fully-filled fixture here passed. Gap-style boundaries (119 / 120) are his too.
    print("== zone bands from real-shaped settings ==")
    pg, errs = fresh()
    REAL = "[{min:null,max:119},{min:120,max:148},{min:149,max:163},{min:164,max:178},{min:179,max:193}]"
    zb = lambda z: pg.evaluate(f"() => {{ Store.data.settings.zones = {z}; return hrZoneBounds(); }}")
    check("⚠️ an open Sone 1 floor still gives bands", zb(REAL) is not None, True)
    check("...as does an open Sone 5 ceiling",
          zb("[{min:null,max:119},{min:120,max:148},{min:149,max:163},{min:164,max:178},{min:179,max:null}]") is not None, True)
    check("a missing boundary in the MIDDLE is still incomplete",
          zb("[{min:null,max:119},{min:120,max:null},{min:149,max:163},{min:164,max:178},{min:179,max:193}]"), None)
    check("an unconfigured editor draws no bands", zb("[]"), None)
    rng = pg.evaluate(f"""() => {{ Store.data.settings.zones = {REAL};
      return hrGraphRange({{ hr: [72, 150, 161], pace: null }}, hrZoneBounds()); }}""")
    check("an open floor does not drag the HR axis below the run", rng["hrLo"], 60)
    check("the top is a labelled round 20, never a bare 163", rng["hrHi"] % 20, 0)
    # His S5 ceiling is open too. Spanning the ladder only means anything if S5 is ON the axis.
    rng5 = pg.evaluate("""() => { Store.data.settings.zones =
        [{min:null,max:127},{min:128,max:157},{min:158,max:170},{min:171,max:180},{min:181,max:null}];
      return hrGraphRange({ hr: [72, 150, 165], pace: null }, hrZoneBounds()); }""")
    check("⚠️ an open S5 ceiling still puts S5 on the axis", rng5["hrHi"] > 181, True)
    pg.close()

    pg, errs = fresh()
    pg.evaluate(f"() => {{ Store.data.settings.zones = {REAL}; }}")
    pg.evaluate(STUB, "ok")
    open_run(pg, "out")
    # Read the pixels: a band is only real if the chart actually painted it.
    tint = pg.evaluate("""() => {
      const c = document.getElementById('hrGraphHr'), ch = Chart.getChart(c), ctx = c.getContext('2d');
      const x = Math.round(ch.chartArea.left + 20), y = Math.round(ch.scales.y.getPixelForValue(135));
      const [r, g, b] = ctx.getImageData(x * devicePixelRatio, y * devicePixelRatio, 1, 1).data;
      return g > r && g > b; }""")
    check("⚠️ ...and on screen the S2 band is actually painted behind the line", tint, True)
    pg.close()

    # Pure helper: the smoothing must not eat an interval's peaks, which is what the graph is FOR.
    pg, errs = fresh()
    peak = pg.evaluate("""() => {
      const time = [], hr = [];
      for (let s = 0; s < 1800; s++) { time.push(s); hr.push(s % 360 < 220 ? 175 : 130); }
      const out = hrGraphSeries({ time:{data:time}, heartrate:{data:hr} });
      return { max: Math.max(...out.hr), min: Math.min(...out.hr), n: out.t.length }; }""")
    check("smoothing keeps an interval's peaks near their real height", peak["max"] > 170, True)
    check("...and its recovery troughs near theirs", peak["min"] < 135, True)
    check("a long stream is thinned to at most ~600 points",
          pg.evaluate("""() => hrGraphSeries({ time:{data:[...Array(14400).keys()]},
              heartrate:{data:Array(14400).fill(140)} }).t.length <= 601"""), True)
    check("a dropped strap (0 bpm) is a gap, never a plunge to zero",
          pg.evaluate("""() => { const h = Array(600).fill(140); for (let i = 200; i < 260; i++) h[i] = 0;
              return Math.min(...hrGraphSeries({ time:{data:[...Array(600).keys()]}, heartrate:{data:h} })
                .hr.filter(x => x != null)) > 130; }"""), True)
    check("a stream with no heart rate at all is null, not an empty chart",
          pg.evaluate("() => hrGraphSeries({ time:{data:[0,1,2]}, heartrate:{data:[0,0,0]} })"), None)
    pg.close()

    # ── The pace strip, after his first real run: squashed, jagged, and labelled with raw
    # percentile edges (5:59, 7:02). Each of those is pinned here.
    print("== the pace strip reads on real-shaped data ==")
    pg, errs = fresh(pace="1")
    # HIS width. At 900 px the step is already 10 and Chart.js never thins, so the dropped-60 bug was
    # invisible there — the mutation restoring what he actually saw passed (falsification, 2026-09-22).
    pg.set_viewport_size({"width": 1180, "height": 1200})
    pg.evaluate("""() => { let seed = 3; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
      StravaIO.fetchActivityStreams = async () => { const time=[], hr=[], vel=[]; let v = 2.5;
        for (let s = 0; s <= 3852; s++) { time.push(s); hr.push(150); v += (2.56 - v) * .08 + (rnd() - .5) * .35; vel.push(v); }
        return { time:{data:time}, heartrate:{data:hr}, velocity_smooth:{data:vel} }; }; }""")
    open_run(pg, "out", wait=600)
    labels = pg.evaluate("""() => Chart.getChart(document.getElementById('hrGraphPace'))
        .scales.y.ticks.map(t => t.label).filter(Boolean)""")
    check("every pace label is a round 30 s", all(l.endswith(":00") or l.endswith(":30") for l in labels), True)
    check("...and there are a readable few of them", 2 <= len(labels) <= 5, True)
    check("the strip is tall enough to show a change as a change",
          pg.evaluate("() => document.getElementById('hrGraphPace').parentElement.offsetHeight") >= 90, True)
    # Noise at the SOURCE is ±0.35 m/s per second; what reaches the screen must be calm. Measured as
    # the largest jump between neighbouring plotted points, in seconds per km.
    jump = pg.evaluate("""() => { const d = Chart.getChart(document.getElementById('hrGraphPace')).data.datasets[0].data;
        let m = 0; for (let i = 1; i < d.length; i++) if (d[i].y != null && d[i-1].y != null)
          m = Math.max(m, Math.abs(d[i].y - d[i-1].y) * 60); return m; }""")
    check("the plotted pace is smooth — no jump over 5 s/km between points", jump < 5, True)
    # His desktop screenshot: a 65 min run whose axis ended at «50 min» — Chart.js's own label
    # thinning dropped the 60 on top of ours. Every round step up to the end must be labelled.
    xs = pg.evaluate("""() => Chart.getChart(document.getElementById('hrGraphPace'))
        .scales.x.ticks.filter(t => t.label).map(t => t.value)""")
    check("⚠️ desktop: the axis labels every round step, up to 60 on his 64 min run",
          (xs[-1], len(set(round(b - a, 6) for a, b in zip(xs, xs[1:])))), (60, 1))
    pg.close()

    # 402 px: the chart and its footer must fit the phone.
    pg = b.new_page(viewport={"width": 402, "height": 900})
    pg.goto(APP); pg.evaluate(HR_SEED); pg.evaluate(TOKEN)
    pg.evaluate("() => localStorage.setItem('lpl_hr_pace', '1')")
    pg.goto(APP); pg.wait_for_timeout(500)
    # ⚠️ 64.2 min, HIS run (zones 1:26 + 28:39 + 34:08). Neither 60 nor 65 exposes the bug: on 60 there
    # is no end to collide with, and on exactly 65 Chart.js's snap tolerance keeps the 60. Between
    # ~60.5 and ~64.6 at this width, includeBounds MOVES the 60 onto the end (second fix, 2026-09-22).
    pg.evaluate("""() => { StravaIO.fetchActivityStreams = async () => {
        const time = [...Array(3853).keys()];
        return { time:{data:time}, heartrate:{data:time.map(() => 150)}, velocity_smooth:{data:time.map(() => 2.5)} }; }; }""")
    open_run(pg, "out", wait=500)
    check("402px: the graph and pace strip draw", pg.evaluate(canvases), 2)
    # Chart.js labels the axis END as well, so a 60-min multiple and a 60-min run end collided into
    # «60 min65 min». Only round multiples of the step may be labelled.
    xl = pg.evaluate("""() => Chart.getChart(document.getElementById('hrGraphPace'))
        .scales.x.ticks.filter(t => t.label).map(t => t.value)""")
    check("402px: the time labels are evenly spaced round steps, never the raw end",
          len(set(round(b - a, 6) for a, b in zip(xl, xl[1:]))) == 1, True)
    check("402px: ...and few enough to fit", len(xl) <= 5, True)
    check("402px: ...reaching the last round step before the end", xl[-1], 60)
    # The STRUCTURAL check, because the symptom is not reproducible here: Chart.js's label thinning
    # depends on real font metrics and never fires headless. On his phone it dropped the 60 because a
    # tick at the axis end sat 5 min away. So assert every tick is a round step and none is the end.
    allx = pg.evaluate("""() => Chart.getChart(document.getElementById('hrGraphPace'))
        .scales.x.ticks.map(t => t.value)""")
    check("⚠️ 402px: every tick is a round step — no tick at the run's raw end",
          all(abs(v - round(v / 10) * 10) < 1e-6 for v in allx), True)
    check("402px: nothing in the graph overflows its panel", pg.evaluate("""() => {
      const g = document.getElementById('hrGraph'), body = document.getElementById('detailBody');
      return g.getBoundingClientRect().right <= body.getBoundingClientRect().right + 1; }"""), True)
    b.close()

print(f"\n{passed}/{passed+failed} passed" + ("" if not failed else f"  ({failed} FAILED)"))
sys.exit(1 if failed else 0)
