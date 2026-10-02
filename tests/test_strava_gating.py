"""Strava-gated controls: disabled + an inline reason when disconnected, live when connected. (2026-08-13)

Standalone — NOT part of run_all.py. Run directly:
    python tests/test_strava_gating.py      (needs Playwright + WebKit)
    PW_ENGINE=firefox python tests/test_strava_gating.py  (also chromium; firefox is his main browser)

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
import os, pathlib, re, sys
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

# Relative to this file, not the repo checkout path — CI clones somewhere else entirely.
APP = (pathlib.Path(__file__).resolve().parent.parent / "puls.html").as_uri()
ENGINE = os.environ.get("PW_ENGINE", "webkit")
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
    b = getattr(p, ENGINE).launch()
    print(f"engine: {ENGINE}")
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
    # ⚠️ ...but moving slowly is not a stop. Strava's `moving` flag marks stretches at 1.2–2.1 m/s
    # «stopped» (his easy run, 01.10), and the line broke wherever a drawn point landed on one. Speed
    # alone decides. The fixture flags a walk AND a 2 s blip at a jog false, as his real streams do;
    # only the real standstill (0 m/s) may stay empty.
    walk = pg.evaluate("""() => {
        const t = [...Array(1500).keys()], hr = t.map(() => 150);
        const vel = t.map(s => s >= 500 && s < 650 ? 1.11 : s >= 1200 && s < 1220 ? 0 : 3.2);
        const moving = t.map(s => !(s >= 500 && s < 650) && !(s >= 900 && s < 902) && !(s >= 1200 && s < 1220));
        const s = hrGraphSeries({ time:{data:t}, heartrate:{data:hr}, velocity_smooth:{data:vel}, moving:{data:moving} });
        const at = sec => s.pace[s.t.findIndex(m => m * 60 >= sec)];
        const r = hrGraphRange(s, hrZoneBounds());
        // Every EMPTY drawn point, in seconds. The line is thinned to every 3rd second here, so a
        // check that reads one moment can miss a 2 s blip entirely (the first version of this one
        // did: it read 903 and passed on the old code) — hence all of them, plus proof a drawn point
        // sits inside the blip.
        const empty = s.t.filter((m, i) => s.pace[i] == null).map(m => Math.round(m * 60));
        return { walk: at(575), stop: at(1210), walkPace: Math.round(at(575)), paceHi: r.paceHi,
                 drawnInBlip: s.t.some(m => Math.round(m * 60) >= 900 && Math.round(m * 60) < 902),
                 strayGaps: empty.filter(sec => sec < 1200 || sec >= 1220) }; }""")
    check("⚠️ a walk Strava calls «stopped» is DRAWN", walk["walk"] is not None, True)
    check("...as walking, well below the walking line", walk["walkPace"] > 3600 / 7.0, True)
    check("a drawn point lands inside the 2 s flag blip (else the next check is vacuous)", walk["drawnInBlip"], True)
    check("a 2 s flag blip at a jog does not cut the line — the standstill is the ONLY gap", walk["strayGaps"], [])
    check("...while a real standstill still does", walk["stop"], None)
    check("...and the axis reaches down to the walk", walk["paceHi"] >= walk["walkPace"], True)

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

    # ── Høyde behind the pace line (2026-09-23) ─────────────────────────────────────────────────
    # It answers «why did the pace give way / the HR climb here», so it rides WITH pace, in the same
    # strip rather than a third one. Outdoor only, and only when the run has real terrain: GPS
    # altitude drifts ~10 m over an hour on its own, so a flat run's silhouette would be noise drawn
    # as a hill. The mockup he picked (A of three, 2026-09-23) is what these pin.
    print("== høyde rides with the pace strip ==")
    pg, errs = fresh(pace="1")
    shape = pg.evaluate("""() => {
      const t = [...Array(1800).keys()], hr = t.map(() => 150), vel = t.map(() => 2.5);
      const hill = t.map(s => 200 + 60 * Math.sin(s / 1800 * Math.PI * 2));   // a 120 m climb and back
      const flat = t.map((s, i) => 200 + (i % 7) * 0.6);                      // 4 m of GPS wobble
      const mk = (alt, o) => hrGraphSeries({ time:{data:t}, heartrate:{data:hr},
        velocity_smooth:{data:vel}, altitude:{data:alt} }, o || {});
      const r = hrGraphRange(mk(hill), hrZoneBounds());
      return { hilly: !!mk(hill).elev, flat: !!mk(flat).elev, tm: !!mk(hill, { treadmill: true }).elev,
               none: !!hrGraphSeries({ time:{data:t}, heartrate:{data:hr}, velocity_smooth:{data:vel} }).elev,
               range: [r.elevLo, r.elevHi] }; }""")
    check("a real climb gives an elevation series", shape["hilly"], True)
    check("⚠️ a flat run does not — 4 m of GPS wobble is not a hill", shape["flat"], False)
    check("a treadmill's altitude is never drawn", shape["tm"], False)
    check("...nor is a run whose stream carries no altitude", shape["none"], False)
    # Snapped to readable 20s and NEVER forced to 0 — a run at 300 m would be a line along the top.
    check("the metre axis is snapped to 20s around the run", shape["range"], [120, 280])
    # On screen: one strip, the hill behind the line, and a caption that says what is down there.
    pg.evaluate("""() => { StravaIO.fetchActivityStreams = async () => { const t = [...Array(1800).keys()];
        return { time:{data:t}, heartrate:{data:t.map(() => 150)}, velocity_smooth:{data:t.map(() => 2.5)},
                 altitude:{data:t.map(s => 200 + 60 * Math.sin(s / 1800 * Math.PI * 2))} }; }; }""")
    open_run(pg, "out", wait=600)
    check("no third canvas — the hill shares the pace strip", pg.evaluate(canvases), 2)
    ds = pg.evaluate("""() => { const c = Chart.getChart(document.getElementById('hrGraphPace'));
        const a = c.chartArea, m = c.getDatasetMeta(1);
        // Where the pace line is actually PLOTTED, which is the check that matters: see below.
        const inside = m.data.filter(p => p.y != null)
          .every(p => p.y >= a.top - 1 && p.y <= a.bottom + 1);
        return { n: c.data.datasets.length, fill: !!c.data.datasets[0].fill,
                 border: c.data.datasets[0].borderWidth, axis: c.data.datasets[0].yAxisID,
                 paceAxis: c.data.datasets[1].yAxisID, paceInside: inside,
                 labels: c.scales.y1.ticks.map(t => t.label) }; }""")
    check("the strip carries the hill and the pace, hill first", (ds["n"], ds["axis"]), (2, "y1"))
    check("...the hill is a fill with no outline", (ds["fill"], ds["border"]), (True, 0))
    check("...read against its own metre axis", all(l.endswith(" m") for l in ds["labels"]), True)
    # ⚠️ THE ONE THAT CAUGHT A REAL BUG, and only because it asks where the line LANDED. A dataset
    # that names no yAxisID takes the FIRST y scale in the options — which became the metre axis the
    # moment it was added, so the pace line was plotted at 8.95 on a 40–220 m scale and clipped out
    # of the strip. Every structural check above passed with the line invisible (2026-09-23).
    check("⚠️ the pace line is measured against the pace axis", ds["paceAxis"], "y")
    check("⚠️ ...so every plotted pace point lands inside the strip", ds["paceInside"], True)
    # Each chart is named where you look at it, rather than by one caption under both (2026-09-23).
    labels = pg.evaluate("""() => [...document.querySelectorAll('#hrGraph .hr-axis-label')]
        .map(e => e.textContent.trim())""")
    check("each chart carries its own label", len(labels), 2)
    check("...the first names the HR chart", labels[0], "Puls (slag/min)")
    check("...the second names pace AND høyde", labels[1], "Tempo (min/km) · høyde (m)")

    # ── Pointing at a moment reads it out; the walking line (his asks, 2026-10-01) ──────────────────
    # The tooltip was off while Chart.js still drew its hover ring — a marker that said nothing. Now
    # either chart reads out time, HR, pace and height at that moment, and one vertical line marks it
    # in both. This stream: HR 150, 2.5 m/s (6:40 /km), a 60 m hill.
    def hover(canvas, fx=0.5):
        box = pg.evaluate(f"() => {{ const r = document.getElementById('{canvas}').getBoundingClientRect();"
                          " return [r.left, r.top, r.width, r.height]; }")
        pg.mouse.move(box[0] + box[2] * fx, box[1] + box[3] * 0.5)
        pg.wait_for_timeout(150)
    READ = """(id) => { const t = Chart.getChart(document.getElementById(id)).tooltip;
        return t.opacity ? [t.title.join(''), ...t.body.flatMap(b => b.lines)] : null; }"""
    hover("hrGraphHr")
    got = pg.evaluate(READ, "hrGraphHr")
    check("pointing at the HR chart reads out the moment: time · HR · pace · height",
          bool(got) and [bool(re.fullmatch(r"\d+:\d\d min", got[0])), got[1], got[2], got[3].endswith(" m")],
          [True, "150 slag/min", "6:40 /km", True])
    # The vertical line is drawn in the OTHER chart too. Read where it must be: a pixel column at the
    # top of the pace strip, before and after — nothing else is drawn there on this run.
    PIX = """() => { const c = Chart.getChart(document.getElementById('hrGraphPace')), cv = c.canvas;
        const k = cv.width / cv.clientWidth, x = c.scales.x.getPixelForValue(window.__crossAt);
        return [...cv.getContext('2d').getImageData(Math.round(x * k), Math.round((c.chartArea.top + 3) * k), 1, 1).data]; }"""
    # The moment under the pointer (hover() points at the middle of the canvas), from the HR chart's own
    # axis — not from its tooltip, so this check stands on the line alone.
    pg.evaluate("""() => { const c = Chart.getChart(document.getElementById('hrGraphHr'));
        window.__crossAt = c.scales.x.getValueForPixel(c.canvas.clientWidth * 0.5); }""")
    pg.mouse.move(2, 2); pg.wait_for_timeout(150)
    away = pg.evaluate(PIX)
    hover("hrGraphHr")
    check("...and marks that moment in the pace strip too", pg.evaluate(PIX) != away, True)
    # A moment must sit directly above itself: the strip's metre axis takes 40 px on the right, and
    # without the same margin on the HR chart the two time axes drifted apart.
    check("...where the two charts put the same minute at the same place", pg.evaluate("""() => {
        const h = Chart.getChart(document.getElementById('hrGraphHr')), p = Chart.getChart(document.getElementById('hrGraphPace'));
        return [5, 15, 25].map(m => Math.round(h.scales.x.getPixelForValue(m) - p.scales.x.getPixelForValue(m))); }"""), [0, 0, 0])
    hover("hrGraphPace", 0.3)
    got = pg.evaluate(READ, "hrGraphPace")
    check("pointing at the pace strip reads out the same three values",
          got and got[1:3], ["150 slag/min", "6:40 /km"])
    pg.mouse.move(2, 2)
    # Walking = slower than 7.0 km/h → 8:34 /km (the run/walk analysis' own threshold). This run sits
    # at 6:40 all the way, so the line is only there because the strip is made to reach it.
    WALK = """() => { const c = Chart.getChart(document.getElementById('hrGraphPace')), cv = c.canvas;
        const k = cv.width / cv.clientWidth;
        const y = c.scales.y, a = c.chartArea, ctx = cv.getContext('2d');
        const walk = 3600 / Continuity.thresholds().definiteWalkMaxKmh / 60;
        const row = Math.round(y.getPixelForValue(walk) * k);
        const px = ctx.getImageData(Math.round(a.left * k), row, Math.round((a.right - a.left) * k), 1).data;
        let amber = 0; for (let i = 0; i < px.length; i += 4) if (px[i] > 200 && px[i+1] > 150 && px[i+1] < 215 && px[i+2] < 130) amber++;
        return { reaches: y.max >= walk, amber: amber > 20 }; }"""
    w = pg.evaluate(WALK)
    check("a steady 6:40 run's strip still reaches the walking line at 8:34", w["reaches"], True)
    check("...and the line is drawn there", w["amber"], True)
    # His thresholds are settings (Innstillinger → Løpekontinuitet): the line follows them.
    pg.evaluate("() => { Store.data.continuitySettings = { walkMaxKmh: 6, runMinKmh: 6.5 }; }")
    open_run(pg, "man"); open_run(pg, "out", wait=600)
    check("...and moves with his own threshold (6.0 km/h → 10:00 /km)",
          pg.evaluate("""() => Chart.getChart(document.getElementById('hrGraphPace')).scales.y.max >= 10"""), True)
    check("no page errors with the hill drawn", errs, [])
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

    # ── The picker dates a run where it was run (2026-09-27) ──────────────────────────────────────
    # Strava's start_date_local is the wall-clock time WHERE the run happened, written with a 'Z' it
    # does not mean. Every stored date takes its first ten characters; the picker's date column parsed
    # the whole string as UTC and let the device's offset move it — in Japan (+9), where he runs later
    # this year, every run after 15:00 showed the NEXT day (Oslo: after 22–23:00). Picking never
    # changes the form's date, so that is how a run gets filed under the wrong day: logged the next
    # morning, yesterday's afternoon run looks like today's. Checked on Tokyo AND Oslo time.
    print("== the Strava picker dates a run where it was run ==")
    PICK = """() => {
      StravaImport.activities = [
        { id: 1, name: 'Morgen',      start_date_local: '2026-11-20T07:00:00Z', distance: 6000 },
        { id: 2, name: 'Ettermiddag', start_date_local: '2026-11-20T15:30:00Z', distance: 8000 },
        { id: 3, name: 'Kveld',       start_date_local: '2026-11-20T23:30:00Z', distance: 5000 }];
      StravaImport._render();
      return [...document.querySelectorAll('#stravaActivityList .dp-session-row')]
        .map(r => r.firstElementChild.textContent.trim()); }"""
    for tz, offset in (("Asia/Tokyo", -540), ("Europe/Oslo", -60)):
        ctx = b.new_context(timezone_id=tz)
        tp = ctx.new_page()
        tp.goto(APP)
        tp.wait_for_timeout(300)
        # Control: the page really runs on that clock — otherwise both passes quietly test one zone.
        check(f"{tz}: control — the page's clock is {tz}",
              tp.evaluate("() => new Date(2026, 10, 20, 12).getTimezoneOffset()"), offset)
        check(f"{tz}: a morning, an afternoon and a late-evening run all read 20.11.2026",
              tp.evaluate(PICK), ['20.11.2026'] * 3)
        ctx.close()

    # ── A fetched run takes its Strava title as Øktnavn (his call, 2026-09-29) ──────────────────────
    # Runna names the workout on Strava («Pyramid Intervals»), which says more than the generated
    # «Runna Intervaller» — whose two halves the log already shows in its PLAN column and type badge.
    # A typed name and a race's 🏁 event name still win, and Strava's time-of-day fallback («Morning
    # Run») is no title, so the generated name stays. A saved run takes it only through «Oppdater fra
    # Strava» (the last checks below). Driven through the real _populate with its two extra Strava
    # requests answered in-page; Form.read() is what a save would store.
    print("== a fetched run takes its Strava title ==")
    tp = b.new_page()
    tp.goto(APP)
    tp.evaluate("""() => {
      StravaIO.fetchActivityDetail = async () => ({ description: '' });
      StravaIO.fetchZones = async () => null;
      Store.data.events = [{ id: 'r1', type: 'race', date: '2026-10-03', title: 'Sentrumsløpet 10K' }];
      switchTab('form');
    }""")
    NAME = """async ({ dato, type, plan, typed, title, after }) => {
      Form.clear();
      const set = (id, v) => { const e = document.getElementById(id); e.value = v; e.dispatchEvent(new Event('change')); };
      set('fDato', dato); set('fOkttype', type); set('fTreningsplan', plan);
      if (typed) document.getElementById('fOktnavn').value = typed;
      const before = document.getElementById('fOktnavn').value;
      await StravaImport._populate({ id: 7, name: title, distance: 7780, moving_time: 2932,
                                     average_speed: 2.65, trainer: true, has_heartrate: false });
      if (after) set('fOkttype', after);
      return [before, Form.read().oktnavn];
    }"""

    def named(**kw):
        return tp.evaluate(NAME, {**dict(dato='2026-09-29', type='Intervaller', plan='Runna', typed='',
                                         title='Pyramid Intervals', after=''), **kw})

    before, name = named()
    check("control: before the fetch the name is the generated «Runna Intervaller»", before, 'Runna Intervaller')
    check("a fetched run takes its Strava title", name, 'Pyramid Intervals')
    check("...and keeps it when the type is changed afterwards", named(after='Tempo')[1], 'Pyramid Intervals')
    check("a name typed before the fetch is kept", named(typed='Bakkeintervaller')[1], 'Bakkeintervaller')
    check("Strava's time-of-day names are no title — the generated name stays",
          [named(title=t)[1] for t in ('Morning Run', 'Ettermiddagsløp')], ['Runna Intervaller'] * 2)
    check("...and neither is a blank one", named(title='   ')[1], 'Runna Intervaller')
    # His REAL time-of-day titles mostly carry the weekday: a run outside the plan is «Monday Evening Run»
    # in his Runna calendar (13 of its 15) and on Strava — 24.07 is «Friday Lunch Run», and he keeps
    # «Runna tempo» for it (2026-09-30). The check above uses only the bare form (#24 again).
    check("his real time-of-day titles carry the weekday — «Friday Lunch Run», any day, is no title either",
          [named(title=t)[1] for t in ('Monday Evening Run', 'Tuesday Lunch Run', 'Wednesday Afternoon Run',
                                       'Thursday Morning Run', 'Friday Lunch Run', 'saturday morning run',
                                       'Sunday Night Run')],
          ['Runna Intervaller'] * 7)
    check("...so an Egentrening run outside the plan stays blank, as with «Evening Run»",
          [named(plan='Egentrening', title=t)[1] for t in ('Thursday Evening Run', 'Evening Run')], ['', ''])
    check("...but only a weekday: anything else in front makes it a name — «Sognsvann Evening Run» stays",
          named(title='Sognsvann Evening Run')[1], 'Sognsvann Evening Run')
    # His point: «regular easy and long runs got no extra sub title». Runna's Strava title for those is
    # the generic «Easy Run»/«Long Run» — the same words the plan card hides (plannedTitle) — so they
    # keep the generated name, and old and new easy runs read alike.
    check("Runna's generic «Easy Run» / «Long Run» is no title either — «Runna Easy» / «Runna Long» stay",
          [named(type='Easy', title='Easy Run')[1], named(type='Long', title='Long Run')[1]],
          ['Runna Easy', 'Runna Long'])
    # His REAL Strava titles carry Runna's distance in front of easy and long runs — «7.5km Easy Run»,
    # «10km Long Run», «11km Progressive Long Run», «5km Race» (his screenshot, 2026-09-30). The check
    # above uses the tidy «Easy Run», so it passed while every real easy run would have been named «7km
    # Easy Run» (#24). The distance goes first, as the plan import already strips it from plan titles.
    check("his real titles: «7.5km Easy Run» / «10km Long Run» still keep «Runna Easy» / «Runna Long»",
          [named(type='Easy', title='7.5km Easy Run')[1], named(type='Long', title='10km Long Run')[1]],
          ['Runna Easy', 'Runna Long'])
    check("...a named long run reads as the plan names it: «11km Progressive Long Run» → «Progressive Long Run»",
          named(type='Long', title='11km Progressive Long Run')[1], 'Progressive Long Run')
    check("...and «5km Race» is no race's name — with no 🏁 event it stays blank",
          named(dato='2026-10-10', type='Race', title='5km Race')[1], '')
    # Only the RUN's distance is redundant. A workout named after its rep keeps it — the plan import
    # has met «1km Repeats • 9km», a 9 km session of 1 km reps.
    check("...but a rep distance is part of the name: «400m Repeats» and «1km Repeats» stay whole",
          [named(title='400m Repeats')[1], named(title='1km Repeats')[1]], ['400m Repeats', '1km Repeats'])
    # The rule itself, as the ONE function the import calls (it was inline in _populate, 8000 lines
    # from the naming helpers it shares a list with) — his real title shapes, no form in between.
    check("stravaWorkoutTitle: his real title shapes, straight to the workout's name or none",
          tp.evaluate("""() => ['7.5km Easy Run', 'Friday Lunch Run', '11km Progressive Long Run', '1km Repeats',
                                 '  Pyramid Intervals ', '5km Race', 'Morgenløp', ''].map(stravaWorkoutTitle)"""),
          ['', '', 'Progressive Long Run', '1km Repeats', 'Pyramid Intervals', '', '', ''])
    check("Egentrening, which had no generated name, gets the title",
          named(plan='Egentrening', title='Tur med Kari')[1], 'Tur med Kari')
    check("a race keeps its 🏁 event's name", named(dato='2026-10-03', type='Race', title='10K race')[1],
          'Sentrumsløpet 10K')
    check("a race with no 🏁 event takes the Strava title rather than a blank",
          named(dato='2026-10-10', type='Race', title='Tønsberg 10K')[1], 'Tønsberg 10K')
    named()   # leaves «Pyramid Intervals» as the last fetched title
    check("a cleared form does not carry the last run's title over", tp.evaluate("""() => {
      Form.clear();
      const set = (id, v) => { const e = document.getElementById(id); e.value = v; e.dispatchEvent(new Event('change')); };
      set('fDato', '2026-09-30'); set('fOkttype', 'Easy'); set('fTreningsplan', 'Runna');
      return document.getElementById('fOktnavn').value; }"""), 'Runna Easy')

    # «Oppdater fra Strava» on a saved run brings its title too (his ask, 2026-09-29) — the per-run way to
    # give an older run its workout's name. Only over a name that says nothing its plan and type columns
    # don't: blank, the generated «Runna Intervaller», or his older hand-typed «Runna intervaller» /
    # «Runna long run». Never over a typed name, never on a race, and nothing is stored until «Oppdater
    # økt». Driven through the real button path, updateCurrent; `retype` changes Økt-type AFTER the click.
    UPD = """async ({ name, type, plan, title, retype, save }) => {
      Store.data.sessions = [{ id: 'e1', dato: '2026-09-22', uke: '2026-39', oktnavn: name, okttype: type,
        treningsplan: plan, varighet: 2700, distanse: 7, soner: [0,0,0,0,0], stravaId: 7 }];
      StravaIO.fetchActivityDetail = async () => ({ id: 7, name: title, description: '', distance: 7000,
        moving_time: 2700, average_speed: 2.6, trainer: false, has_heartrate: false });
      Form.editSession('e1');
      await StravaImport.updateCurrent();
      if (retype) { const e = document.getElementById('fOkttype'); e.value = retype; e.dispatchEvent(new Event('change')); }
      const got = [Form.read().oktnavn, Store.data.sessions[0].oktnavn];
      if (save) { Form.save(); got.push(Store.data.sessions[0].oktnavn); } else Form.cancelEdit();
      return got;
    }"""

    def updated(**kw):
        return tp.evaluate(UPD, {**dict(name='Runna Intervaller', type='Intervaller', plan='Runna',
                                        title='Pyramid Intervals', retype='', save=False), **kw})

    check("«Oppdater fra Strava»: a generated name takes the title — in the form, not yet stored",
          updated(), ['Pyramid Intervals', 'Runna Intervaller'])
    check("...and «Oppdater økt» stores it", updated(save=True)[2], 'Pyramid Intervals')
    check("...and so do his older spellings «Runna intervaller» / «Runna long run»",
          [updated(name='Runna intervaller')[0],
           updated(name='Runna long run', type='Long', title='Progressive Long Run')[0]],
          ['Pyramid Intervals', 'Progressive Long Run'])
    check("...and a blank name", updated(name='', plan='Egentrening', title='Tur med Kari')[0], 'Tur med Kari')
    check("a typed name stays", updated(name='Bakkeintervaller')[0], 'Bakkeintervaller')
    check("Strava's time-of-day and generic titles are no title here either",
          [updated(name='Runna Easy', type='Easy', title=t)[0] for t in ('Morning Run', 'Easy Run')],
          ['Runna Easy'] * 2)
    check("...nor a weekday one: 24.07's «Runna tempo» survives its «Friday Lunch Run»",
          updated(name='Runna tempo', type='Tempo', title='Friday Lunch Run')[0], 'Runna tempo')
    check("...nor is his real «7km Easy Run», and «11km Progressive Long Run» arrives without its distance",
          [updated(name='Runna Easy', type='Easy', title='7km Easy Run')[0],
           updated(name='Runna Long', type='Long', title='11km Progressive Long Run')[0]],
          ['Runna Easy', 'Progressive Long Run'])
    check("a race keeps its own name, even a blank one",
          updated(name='', type='Race', title='Tønsberg 10K')[0], '')
    check("...and changing the type after the click renames nothing — only the click takes the title",
          updated(name='', type='Race', title='Tønsberg 10K', retype='Tempo')[0], '')
    tp.close()
    b.close()

print(f"\n{passed}/{passed+failed} passed" + ("" if not failed else f"  ({failed} FAILED)"))
sys.exit(1 if failed else 0)
