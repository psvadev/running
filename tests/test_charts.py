"""Mål km overlay on Ukentlig distanse, and the two cards it replaced.  (2026-08-25)

Standalone — NOT part of run_all.py, which is the fast no-browser gate. Run directly:
    python tests/test_charts.py           (needs Playwright + WebKit)

Treningskalender was removed (unused in practice) and "Plan vs faktisk — distanse" was folded into
Ukentlig distanse as an opt-in overlay: its bars were the SAME weekly kilometres this chart already
plotted, so only the dashed target line was ever unique.

NOTHING tested either card before, on any surface. What this pins is the two rules that are easy to
break silently and impossible to see in a screenshot:

  1. A WEEK WITH NO TARGET IS A GAP, NOT A ZERO. `null` makes Chart.js break the line, which reads
     as "nothing was planned". A 0 would draw the line to the floor and look like a missed week.
  2. THE OVERLAY IS WEEK-MODE ONLY, and that is correctness, not taste. Only weeks carrying a target
     contribute one, so a month where 2 of 4 weeks were planned sums to a half-size target while the
     bar shows the full month — it would read as "wildly over plan" when it is really missing data.

The fixture carries one week per verdict band plus one deliberately untargeted week, so rule 1 and
all four bullet colours are exercised together.

No local data file exists; every session is synthesised in-page.
"""
import pathlib, re, sys, tempfile
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

APP = (pathlib.Path(__file__).resolve().parent.parent / "puls.html").as_uri()
passed = failed = 0


def check(name, got, want):
    global passed, failed
    if got == want:
        passed += 1
        print(f"  PASS {name}")
    else:
        failed += 1
        print(f"  FAIL {name}\n       got  {got!r}\n       want {want!r}")


# Two weeks with targets, one without — so the overlay must draw a GAP, not a zero.
SEED = """() => {
  const run = (id, dato, uke, distanse, mal) => ({
    id, dato, uke, oktnavn:'Tur', okttype:'Easy', treningsplan:'Runna',
    løpetype:'utendors', distanse, varighet: distanse*360, tempo:360,
    soner:[0,10,20,0,0], malDistanse: mal,
  });
  localStorage.setItem('lpl_cache', JSON.stringify({
    sessions:[
      run('a','2026-08-03','2026-32',10,12), run('b','2026-08-05','2026-32',8,8),  // 18/20 = 90%  near
      run('c','2026-08-10','2026-33',15,12),                                       // 15/12 = 125% over
      run('d','2026-08-17','2026-34',9,null),                                      // no target at all
      run('e','2026-08-24','2026-35',10,10),                                       // 10/10 = 100% reached
      run('f','2026-08-31','2026-36',5,10),                                        //  5/10 = 50%  under
    ],
    shoes:[], shoeDefaults:{}, goals:{}, events:[], plannedSessions:[],
    settings:{zones:[]}, lastUpdated:'' }));
}"""

with sync_playwright() as pw:
    b = pw.webkit.launch()
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("dialog", lambda d: d.accept())
    pg.goto(APP); pg.evaluate(SEED); pg.goto(APP)
    pg.wait_for_timeout(800)
    pg.evaluate("() => switchTab('dash')")
    pg.wait_for_timeout(700)

    print("== the two removed cards are gone ==")
    for sel, label in [("#heatmapCard", "Treningskalender card"),
                       ("#heatmapContainer", "heatmap container"),
                       ("#hmTooltip", "heatmap tooltip element"),
                       ("#planActualCard", "Plan vs faktisk card"),
                       ("#chartPlanActual", "Plan vs faktisk canvas")]:
        check(f"{label} absent", pg.evaluate(f"() => !!document.querySelector('{sel}')"), False)
    check("renderHeatmap is undefined",
          pg.evaluate("() => typeof renderHeatmap"), "undefined")
    check("no 'Treningskalender' text on the dashboard",
          "Treningskalender" in pg.locator("#panel-dash").inner_text(), False)
    check("no 'Plan vs faktisk' text on the dashboard",
          "Plan vs faktisk" in pg.locator("#panel-dash").inner_text(), False)

    print("== the weekly distance chart still works ==")
    check("chart exists", pg.evaluate("() => !!Charts.weeklyDist"), True)
    check("one dataset while the box is unchecked",
          pg.evaluate("() => Charts.weeklyDist.data.datasets.length"), 1)
    check("Mål km checkbox is offered (targets exist)",
          pg.evaluate("() => getComputedStyle(document.getElementById('distTargetWrap')).display"), "flex")

    print("== ticking Mål km adds the overlay ==")
    pg.check("#distShowTarget"); pg.wait_for_timeout(400)
    ds = pg.evaluate("() => Charts.weeklyDist.data.datasets.map(d => ({l:d.label, t:d.type, d:d.data}))")
    check("two datasets", len(ds), 2)
    check("overlay is a line named 'Mål km'", (ds[1]["l"], ds[1]["t"]), ("Mål km", "line"))
    check("wk32 target = 12+8 = 20", ds[1]["d"][0], 20)
    check("wk33 target = 12", ds[1]["d"][1], 12)
    check("⚠️ untargeted week is null (a GAP), not 0", ds[1]["d"][2], None)
    check("actual bars unchanged", ds[0]["d"], ["18.00", "15.00", "9.00", "10.00", "5.00"])

    # The verdict is carried by the BULLETS. Bars stay uniform — colouring them would collide with
    # this chart's default blue and make an untargeted week look like one that beat its target.
    pts = pg.evaluate("() => Charts.weeklyDist.data.datasets[1].pointBackgroundColor")
    check("90 % → amber (near)", pts[0], "rgba(240,192,80,1)")
    check("125 % → blue (over)", pts[1], "rgba(108,143,255,1)")
    check("⚠️ no target → transparent bullet, not a coloured verdict", pts[2], "transparent")
    check("100 % → green (reached)", pts[3], "rgba(75,190,120,1)")
    check("50 % → red (under)", pts[4], "rgba(224,85,85,1)")
    check("every bullet gets a rim so 'over' stays visible on the bar",
          pg.evaluate("() => Charts.weeklyDist.data.datasets[1].pointBorderColor"), "#e8eaf0")
    check("bars are still one uniform colour",
          pg.evaluate("() => typeof Charts.weeklyDist.data.datasets[0].backgroundColor"), "string")
    check("legend shown only with the overlay",
          pg.evaluate("() => Charts.weeklyDist.options.plugins.legend.display"), True)

    print("== Måned mode hides it — summing partial targets would lie ==")
    pg.click("#distToggleMaaned"); pg.wait_for_timeout(400)
    check("checkbox hidden in month mode",
          pg.evaluate("() => getComputedStyle(document.getElementById('distTargetWrap')).display"), "none")
    check("no overlay dataset in month mode",
          pg.evaluate("() => Charts.weeklyDist.data.datasets.length"), 1)

    print("== Nullstill resets it ==")
    pg.click("#distToggleWeek"); pg.wait_for_timeout(300)
    pg.check("#distShowTarget"); pg.wait_for_timeout(300)
    pg.click("#btnDashReset"); pg.wait_for_timeout(600)
    check("checkbox cleared", pg.evaluate("() => document.getElementById('distShowTarget').checked"), False)
    check("back to one dataset", pg.evaluate("() => Charts.weeklyDist.data.datasets.length"), 1)

    print("== the overlay is forced off on load ==")
    # NOT tested by "tick it, reload, assert false" — that passes VACUOUSLY here, because WebKit
    # does not restore form state in the first place. Chromium does, which is why the box survived
    # F5 in Edge but nowhere else. So prove the forcing directly: load a copy whose markup already
    # says `checked` and assert init cleared it. Without the fix this stays ticked and the overlay
    # renders unasked.
    src = pathlib.Path(__file__).resolve().parent.parent / "puls.html"
    html = src.read_text(encoding="utf-8")
    marker = '<input type="checkbox" id="distShowTarget">'
    assert html.count(marker) == 1, "checkbox markup moved — update this test"
    # Written to the SYSTEM temp dir, never beside puls.html: a run killed between write and unlink
    # would otherwise leave a stray .html in a public repo folder. puls.html is self-contained, so a
    # copy runs correctly from anywhere.
    tmp = pathlib.Path(tempfile.gettempdir()) / "_charts_checked_probe.html"
    tmp.write_text(html.replace(marker, marker[:-1] + " checked>"), encoding="utf-8")
    try:
        pg.goto(tmp.as_uri()); pg.wait_for_timeout(800)
        pg.evaluate("() => switchTab('dash')"); pg.wait_for_timeout(600)
        check("a pre-checked box is cleared by init",
              pg.evaluate("() => document.getElementById('distShowTarget').checked"), False)
        check("...so no overlay dataset is drawn unasked",
              pg.evaluate("() => Charts.weeklyDist.data.datasets.length"), 1)
    finally:
        tmp.unlink(missing_ok=True)

    pg.goto(APP); pg.wait_for_timeout(800)
    pg.evaluate("() => switchTab('dash')"); pg.wait_for_timeout(600)

    print("== 402 px ==")
    # POLL, don't sleep-and-hope. A fixed wait here failed ~1 run in 4: the Nullstill above kicks off
    # a full renderDashboard, and Chart.js canvases can still be mid-resize when the viewport changes,
    # so the page transiently measures wider than the viewport. Probed it — the steady state is clean
    # at every sample from 250 ms on, and the widest element (#weeklyTable, 450 px) lives inside its
    # own overflow-x:auto card, so it never pushes the page.
    # This still fails on a REAL overflow: that never settles, so the loop just runs out.
    # ⚠️ 2026-09-05: this went RED in pre-push while passing 3/3 standalone, on a change that touched
    # only the log tab (measured: no overflow on either tab at 402 px). The bug was in the check, not
    # the app. The old version broke out of the loop on success and asserted a bare bool, so RUNNING
    # OUT OF BUDGET and REAL OVERFLOW produced the identical failure — and under pre-push, with 15
    # browser suites back to back, the render simply needs longer than 20x150 ms to settle.
    # Now it keeps the last MEASUREMENT and reports it: a failure says how many pixels wide the page
    # actually was, so "0" (a timing artefact) can never again be mistaken for a real overflow.
    pg.set_viewport_size({"width": 402, "height": 900})
    over = None
    for _ in range(40):                       # 6 s, generous enough for a loaded machine
        pg.wait_for_timeout(150)
        over = pg.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
        if over <= 1:
            break
    check(f"no horizontal overflow (settled, last measured {over:+} px)", over <= 1, True)

    # ── One number, one name (2026-09-08) ───────────────────────────────────────────────────────
    # The weekly-session threshold is shown on three surfaces and had drifted to THREE different
    # names — «Mål løp/uke» in the Hendelser plan form, «Løp-grense per uke» in Innstillinger and
    # «N+ løp/uke» on the Treningsrytme tile. Renamed to «økt» together: in Norwegian «løp» is both a
    # run and a RACE, and the plan field sits beside the race settings, where "Mål løp/uke" reads as
    # "target races per week". This pins that they keep agreeing — copy drift is silent, and this is
    # the drift that already happened once.
    print("== the weekly-session threshold has ONE name ==")
    pg.set_viewport_size({"width": 1280, "height": 900})
    pg.evaluate("() => switchTab('dash')")
    pg.wait_for_timeout(400)
    labels = pg.evaluate("""() => ({
        plan: document.getElementById('newEvtRunTarget').placeholder,
        inst: document.querySelector('label[for], .form-group label') && [...document.querySelectorAll('.form-group label')]
                .map(l => l.textContent).find(t => t.includes('grense per uke') && t.includes('Økt')) || '',
        tile: document.getElementById('consistencyContent').textContent })""")
    check("plan-event field says økter/uke", 'økter/uke' in labels['plan'], True)
    check("Innstillinger says Økt-grense", labels['inst'], 'Økt-grense per uke')
    check("Treningsrytme tile says økter/uke", 'økter/uke' in labels['tile'], True)
    # Positive control: the tile really did render, so the assertion above had text to inspect —
    # an empty #consistencyContent would fail it, but for the wrong reason.
    check("control: the tile rendered at all", 'uker' in labels['tile'], True)
    # And the old word is gone from all three, not merely joined by the new one.
    check("no surface still says løp/uke",
          any('løp/uke' in v for v in labels.values()), False)

    # ── Counts say «økt» too (2026-09-18) ───────────────────────────────────────────────────────
    # The rename above stopped at the threshold; every drill-down count tile still said «3 løp»
    # beside «Denne uken»'s «3 økter». One word for a session, singular at 1.
    print("== a session count says økt/økter, never løp ==")
    def week_tiles(wk):
        pg.evaluate(f"() => DetailPanel.openWeek('{wk}', Store.data.sessions)")
        pg.wait_for_timeout(300)
        t = pg.evaluate("""() => ({
            labels: [...document.querySelectorAll('#detailBody .dpl')].map(e => e.textContent.trim()),
            body: document.getElementById('detailBody').innerText })""")
        pg.keyboard.press("Escape"); pg.wait_for_timeout(200)
        return t
    two, one = week_tiles('2026-32'), week_tiles('2026-33')
    check("two sessions → «økter» tile", 'økter' in two['labels'], True)
    check("one session → «økt» tile", 'økt' in one['labels'], True)
    check("no tile is labelled «løp»", 'løp' in two['labels'] + one['labels'], False)
    check("no «N løp» anywhere in either panel",
          bool(re.search(r'\d\s*løp\b', two['body'] + one['body'])), False)

    # ── Løpetype and Tempo-enhet are pills, not radios (his pick, 2026-09-27) ───────────────────────
    # They were the only radio buttons left among the app's toggles. What must survive the change is
    # BEHAVIOUR, so a click has to filter the dashboard (asserted on the weekly table, not on
    # DashFilter), the state has to be announced (aria-pressed, as a radio's checked state was), the
    # keyboard has to reach them, and Nullstill has to put both groups back.
    print("== Løpetype and Tempo-enhet are pills ==")
    pg.set_viewport_size({"width": 1280, "height": 900})
    pg.evaluate("() => switchTab('dash')")
    pg.wait_for_timeout(400)
    PRESSED = """() => ['dfVenuePills', 'dfUnitPills'].map(id =>
      [...document.querySelectorAll(`#${id} .year-pill`)]
        .filter(p => p.getAttribute('aria-pressed') === 'true' && p.classList.contains('active'))
        .map(p => p.textContent.trim()))"""
    rows = lambda: pg.locator('#weeklyBody tr').count()
    check("no radio buttons left in the filter bar",
          pg.evaluate("() => document.querySelectorAll('#dashFilterBar input[type=radio]').length"), 0)
    check("defaults: exactly Alle and min/km pressed", pg.evaluate(PRESSED), [['Alle'], ['min/km']])
    before = rows()
    check("control: the weekly table has rows to lose", before > 0, True)
    pg.click('#dfVenuePills [data-venue="treadmill"]')
    pg.wait_for_timeout(400)
    check("⚙️ Inne filters the dashboard (this fixture has no belt runs)", rows(), 0)
    check("...and is the one pressed", pg.evaluate(PRESSED)[0], ['⚙️ Inne'])
    pg.focus('#dfUnitPills [data-unit="kmh"]')
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(300)
    check("the keyboard reaches them: Enter on km/t presses it", pg.evaluate(PRESSED)[1], ['km/t'])
    pg.click("#btnDashReset")
    pg.wait_for_timeout(600)
    check("Nullstill puts both groups back", pg.evaluate(PRESSED), [['Alle'], ['min/km']])
    check("...and the dashboard with them", rows(), before)
    # They should read as the År pills beside them, not merely share a class name.
    heights = pg.evaluate("""() => ['#dfVenuePills .year-pill', '#dfYearPills .year-pill']
        .map(s => Math.round(document.querySelector(s).getBoundingClientRect().height))""")
    check(f"the same height as the År pills ({heights[0]} vs {heights[1]} px)", heights[0] == heights[1], True)

    # ── Phones: the filter bar is one line that opens (his pick B, 2026-09-27) ─────────────────────
    # The full bar took ~210 px of the first screen. Closed, only the summary shows, naming what
    # changes the numbers as pills. What would fail silently: a pill missing because its handler never
    # told the summary (the unit path does NOT re-render the dashboard), an inline-styled child showing
    # through the collapse, and a hand-typed plan name reaching innerHTML raw.
    print("== phone: the filter bar is one line that opens ==")
    PLAN = '<i>Min plan</i>'
    SUMSEED = """(plan) => {
      const run = (id, dato, uke, p) => ({ id, dato, uke, oktnavn:'Tur', okttype:'Easy', treningsplan:p,
        løpetype:'utendors', distanse:8, varighet:2880, tempo:360, soner:[0,10,20,0,0] });
      localStorage.setItem('lpl_cache', JSON.stringify({
        sessions: [run('a','2026-08-03','2026-32','Runna'), run('b','2026-08-10','2026-33', plan)],
        customPlans: [plan], shoes:[], shoeDefaults:{}, goals:{}, events:[], plannedSessions:[],
        settings:{zones:[]}, lastUpdated:'' }));
    }"""
    SUM = """() => { const bar = document.getElementById('dashFilterBar'), s = document.getElementById('dfSummary');
      return { visible: [...bar.children].filter(c => c.getBoundingClientRect().height > 0).map(c => c.id || c.tagName),
               height: Math.round(bar.getBoundingClientRect().height),
               pills: [...s.querySelectorAll('.df-sum-v .year-pill')].map(p => p.textContent),
               text: s.querySelector('.df-sum-v').textContent.trim(),
               expanded: s.getAttribute('aria-expanded'),
               raw: s.querySelectorAll('.df-sum-v i').length }; }"""
    pg3 = b.new_page(viewport={"width": 402, "height": 900})
    pg3.on("pageerror", lambda e: errs.append(str(e)))
    pg3.goto(APP); pg3.evaluate(SUMSEED, PLAN); pg3.goto(APP)
    pg3.wait_for_timeout(600)
    pg3.evaluate("() => switchTab('dash')")
    pg3.wait_for_timeout(600)
    s = pg3.evaluate(SUM)
    check("402 px: closed, only the summary line shows", s['visible'], ['dfSummary'])
    check(f"...one line, not the full bar ({s['height']} px)", s['height'] < 60, True)
    check("...and with nothing set it says so", (s['text'], s['pills']), ('Alle økter, alle år', []))
    pg3.click('#dfSummary')
    pg3.wait_for_timeout(200)
    s = pg3.evaluate(SUM)
    check("a tap opens the full bar", (s['expanded'], len(s['visible']) > 5), ('true', True))
    pg3.click('#dfVenuePills [data-venue="utendors"]')
    pg3.wait_for_timeout(300)
    pg3.select_option('#dfPlan', PLAN)
    pg3.wait_for_timeout(300)
    pg3.click('#dfUnitPills [data-unit="kmh"]')
    pg3.wait_for_timeout(300)
    s = pg3.evaluate(SUM)
    check("every filter set — and km/t, which re-renders nothing — is a pill", s['pills'], [PLAN, '🏃 Ute', 'km/t'])
    check("⚠️ a hand-typed plan name is text, not markup", s['raw'], 0)
    pg3.click('#dfSummary')
    pg3.wait_for_timeout(200)
    check("a second tap closes it again", pg3.evaluate(SUM)['visible'], ['dfSummary'])
    pg3.click('#dfSummary')
    pg3.click('#btnDashReset')
    pg3.wait_for_timeout(600)
    check("Nullstill empties the summary", pg3.evaluate(SUM)['text'], 'Alle økter, alle år')
    pg3.set_viewport_size({"width": 1280, "height": 900})
    pg3.wait_for_timeout(300)
    check("desktop: no summary line, the full bar as before",
          (pg3.evaluate("() => getComputedStyle(document.getElementById('dfSummary')).display"),
           pg3.locator('#dfType').is_visible()), ('none', True))
    pg3.close()

    # ── Narrow desktop windows (2026-09-27) ────────────────────────────────────────────────────────
    # A grid item's minimum width is its content's. Sko oversikt beside Ukentlig oversikt — the only
    # half-width pair; the table alone needs ~555 px — needs 835 px of grid side by side. Two columns
    # used to start at 769 px, so between there and ~875 px both columns overflowed: every card grew
    # wider than the window (835 px cards on 800) and every chart redrew at that width and held it.
    # Now the grid stays one column until the pair fits (880 px), and in one column the cards may
    # shrink below their content. Side by side the pair keeps content-aware widths: min-width:0 on it
    # made the halves equal and pushed the table behind a scroll at 900 px (the 900 px check caught it).
    # ⚠️ The CONTROL is what makes the 800 px checks non-vacuous: it proves this fixture's pair could
    # NOT sit side by side there. The first diagnosis blamed Formkurve's canvas; canvases only follow.
    # Walked as one narrowing window, 1280 → 900 → 800, because crossing from two columns into one is
    # where a chart drawn wide held its card open (860 px on 800 without min-width:0). A 1000 px step
    # was dropped: in two columns a card spanning both is not measured for the column widths, so a
    # check there could never fail on this (falsification, 2026-09-27).
    print("== narrow desktop windows: cards fit, the pair stacks until it fits ==")
    SHOES = """() => {
      const run = (id, dato, uke, distanse, sko) => ({ id, dato, uke, oktnavn:'Tur', okttype:'Easy',
        treningsplan:'Runna', løpetype:'utendors', distanse, varighet: distanse*360, tempo:360,
        soner:[0,10,20,0,0], sko });
      localStorage.setItem('lpl_cache', JSON.stringify({
        sessions: [run('a','2026-08-03','2026-32',10,'Saucony Endorphin Speed 5'),
                   run('b','2026-08-10','2026-33',12,'Nike Pegasus 41 Premium'),
                   run('c','2026-08-17','2026-34',9,'Saucony Endorphin Speed 5'),
                   run('d','2026-08-24','2026-35',14,'Nike Pegasus 41 Premium')],
        shoes: [{ name:'Saucony Endorphin Speed 5', startKm:0, retired:false, retirementKm:700 },
                { name:'Nike Pegasus 41 Premium', startKm:120, retired:false, retirementKm:800 }],
        shoeDefaults:{}, goals:{}, events:[], plannedSessions:[], settings:{zones:[]}, lastUpdated:'' }));
    }"""
    WIDTHS = """() => { const g = document.querySelector('#panel-dash .dash-grid');
      const mc = el => { const w0 = el.style.width; el.style.width = 'min-content';
                         const w = el.getBoundingClientRect().width; el.style.width = w0; return w; };
      const cards = [...g.children].filter(c => c.offsetParent);
      const half = cards.filter(c => !c.classList.contains('span2'));
      // Ink past a card's right edge, anywhere except inside a scroll container (that is where the
      // weekly table is supposed to go when its card is narrower than it).
      const scrolls = el => { for (let a = el.parentElement; a && a !== g; a = a.parentElement)
          if (getComputedStyle(a).overflowX !== 'visible') return true; return false; };
      const spills = cards.flatMap(c => { const right = c.getBoundingClientRect().right;
          return [...c.querySelectorAll('*')].filter(el => el.getBoundingClientRect().right > right + 1 && !scrolls(el))
                   .slice(0, 1).map(el => el.tagName.toLowerCase() + (el.id ? '#' + el.id : '')); });
      // How much of the weekly table is hidden behind a scroll inside its own card.
      let wrap = document.getElementById('weeklyTable').parentElement;
      while (wrap && getComputedStyle(wrap).overflowX === 'visible') wrap = wrap.parentElement;
      return { grid: g.clientWidth, cols: getComputedStyle(g).gridTemplateColumns.split(' ').length,
               halves: half.length, halfNeed: half.reduce((s, c) => s + mc(c), 0) + parseFloat(getComputedStyle(g).columnGap),
               widest: Math.max(...cards.map(c => c.getBoundingClientRect().width)), spills,
               tableHidden: wrap ? wrap.scrollWidth - wrap.clientWidth : 0 }; }"""
    pg2 = b.new_page(viewport={"width": 1280, "height": 900})
    pg2.on("pageerror", lambda e: errs.append(str(e)))
    # Clock frozen INSIDE a week that has a run (Tue 2026-08-18, run 'c' on the 17th): the current
    # week's row then carries its «Denne uken» tag, which is what widens the table's first column to
    # his real shape. On the live clock no fixture week is current, the table is ~90 px narrower, and
    # the pair fits — the control caught exactly that.
    pg2.add_init_script("""(() => { const R = Date, fixed = new R(2026, 7, 18, 12, 0, 0).getTime();
      function F(...a) { return a.length ? new R(...a) : new R(fixed); }
      F.prototype = R.prototype; F.now = () => fixed; F.parse = R.parse; F.UTC = R.UTC; window.Date = F; })();""")
    pg2.goto(APP); pg2.evaluate(SHOES); pg2.goto(APP)
    pg2.wait_for_timeout(600)
    pg2.evaluate("() => switchTab('dash')")
    # Settle first: measured at 150 ms the two cards were not filled yet, so the control read a pair
    # that fitted — and a stretch check on an empty dashboard passes for the wrong reason.
    pg2.wait_for_timeout(700)

    def settle(width):
        # Polled, like the 402 px check above: charts resize a beat after layout, and a canvas still
        # at its old width reads as a stretch. The last measurement is what gets reported.
        pg2.set_viewport_size({"width": width, "height": 900})
        for _ in range(30):
            pg2.wait_for_timeout(150)
            m = pg2.evaluate(WIDTHS)
            if m['widest'] <= m['grid'] + 0.5 and not m['spills'] and m['tableHidden'] <= 1:
                break
        return m

    w = settle(900)
    check(f"900 px — control: two columns, and the pair fits side by side ({w['halfNeed']:.0f} of {w['grid']} px)",
          (w['cols'], w['halves'], w['halfNeed'] <= w['grid']), (2, 2, True))
    check("900 px — no card is wider than the grid, and the table is whole",
          (w['widest'] <= w['grid'] + 0.5, w['tableHidden'] <= 1), (True, True))
    w = settle(800)
    check(f"800 px — control: side by side, the pair would NOT fit ({w['halfNeed']:.0f} of {w['grid']} px)",
          (w['halves'], w['halfNeed'] > w['grid']), (2, True))
    check("800 px — so the grid is one column and the pair stacks", w['cols'], 1)
    check(f"800 px — no card is wider than the grid (widest {w['widest']:.0f} of {w['grid']} px)",
          w['widest'] <= w['grid'] + 0.5, True)
    check(f"800 px — the weekly table is whole, not behind a scroll ({w['tableHidden']} px hidden)",
          w['tableHidden'] <= 1, True)
    check("800 px — and nothing spills out of its card", w['spills'], [])
    pg2.close()

    # ── Week axes: the number alone, flat, the year said once (his pick B, 2026-09-28) ─────────────
    # «Uke 05 '26» under every bar tilted 27° on a laptop and 45° on a phone, where Chart.js then named
    # only 9 of 26 weeks. Now a tick is the zero-padded week number and «uke · 2025–26» sits once under
    # the axis. Measured on the RENDERED scale — Chart.js's own labelRotation and the ticks it kept —
    # not on the options (#26). What would fail silently: a number under the WRONG bar (every tick is
    # checked against the label of the bar it sits under), the tooltip losing its full «Uke 01 '26»
    # (data.labels changed instead of the tick text), and a title that misses a New Year — the
    # fixture's 30 weeks cross one, so «52 01» and «2025–26» are both in view. All eight weekly charts
    # render, including the two that need a current Strava analysis.
    print("== week axes: the number alone, flat, the year once ==")
    WEEKLY = ['load', 'weeklyDist', 'pace', 'venue', 'elev', 'zones', 'contTrend', 'aeroTrend']
    AXSEED = """() => {
      const thr = Continuity.thresholds();
      const cont = { version: CONTINUITY_ANALYSIS_VERSION, thresholdVersion: CONTINUITY_THRESHOLD_VERSION,
        walkMaxKmh: thr.definiteWalkMaxKmh, runMinKmh: thr.definiteRunMinKmh,
        movingTimeSeconds: 3000, runningTimeSeconds: 2800, walkingTimeSeconds: 100,
        unclassifiedTimeSeconds: 100, stoppedTimeSeconds: 0, runningRatio: 0.93, walkingRatio: 0.03,
        unclassifiedRatio: 0.04, runningDistanceMeters: 8000, walkingDistanceMeters: 200,
        unclassifiedDistanceMeters: 200, longestContinuousRunSeconds: 1200, longestContinuousRunMeters: 3100,
        runToWalkTransitions: 2, uphillWalkingTimeSeconds: 10, uphillWalkingDistanceMeters: 18,
        sampleCount: 3000, datakvalitet: 'høy', warnings: [] };
      const aero = { version: AEROBIC_ANALYSIS_VERSION, hasDecoupling: true, decouplingPercent: 4,
        hasCadence: true, avgCadenceSpm: 168 };
      const sessions = [];
      // A Wednesday in each of 30 weeks, ISO 2025-40 through 2026-17 (ISO 2025 has 52 weeks); the
      // charts keep the last 26, 2025-44 to 2026-17. A belt run every fifth week for Ute/inne.
      for (let w = 0; w < 30; w++) {
        const d = new Date(Date.UTC(2025, 9, 1) + w * 7 * 864e5).toISOString().slice(0, 10);
        sessions.push({ id: 'u' + w, dato: d, uke: isoWeek(d), oktnavn: 'Tur', okttype: 'Easy',
          treningsplan: 'Runna', løpetype: 'utendors', distanse: 8, varighet: 2880, tempo: 360,
          hoydeMeter: 60, soner: [0, 600, 1200, 0, 0], stravaId: 's' + w,
          stravaAnalysis: { continuity: cont, aerobic: aero } });
        if (w % 5 === 0) sessions.push({ id: 't' + w, dato: d, uke: isoWeek(d), oktnavn: 'Belte',
          okttype: 'Easy', treningsplan: 'Runna', løpetype: 'treadmill', distanse: 5, varighet: 1800,
          tempo: 360, soner: [0, 600, 600, 0, 0] });
      }
      localStorage.setItem('lpl_cache', JSON.stringify({ sessions, shoes: [], shoeDefaults: {}, goals: {},
        events: [], plannedSessions: [], settings: { zones: [] }, lastUpdated: '' }));
    }"""
    AXES = """(names) => names.map(n => { const c = Charts[n]; if (!c) return { n, missing: true };
      const x = c.scales.x;
      return { n, width: c.width, rot: Math.round(x.labelRotation), labels: c.data.labels,
               sets: c.data.datasets.length, ticks: x.ticks.map(t => ({ v: t.value, l: t.label })),
               title: x.options.title && x.options.title.display ? x.options.title.text : null }; })"""
    # The tooltip title of one bar, raised the way a hover raises it — on the first dataset that has
    # a value there (Årssammenligning's 2025 line has none in January).
    TIP = """([n, i]) => { const c = Charts[n], d = Math.max(0, c.data.datasets.findIndex(s => s.data[i] != null));
      c.tooltip.setActiveElements([{ datasetIndex: d, index: i }], { x: 0, y: 0 }); c.update('none');
      const t = c.tooltip.title; c.tooltip.setActiveElements([], { x: 0, y: 0 }); c.update('none'); return t; }"""

    def axes(page, width):
        # Polled: Chart.js resizes a beat after the viewport does, and a scale read mid-resize still
        # carries the old width's rotation. The last entry is Årssammenligning.
        page.set_viewport_size({"width": width, "height": 900})
        for _ in range(40):
            page.wait_for_timeout(150)
            a = page.evaluate(AXES, WEEKLY + ['yearComp'])
            if all(not x.get('missing') and x['width'] <= width for x in a):
                break
        return a

    def misplaced(a):
        # Ticks whose number is not the week of the bar they sit under.
        return [(t['l'], a['labels'][t['v']]) for t in a['ticks']
                if f"Uke {t['l']} '" not in a['labels'][t['v']]]

    pg4 = b.new_page(viewport={"width": 1280, "height": 900})
    pg4.on("pageerror", lambda e: errs.append(str(e)))
    pg4.goto(APP); pg4.evaluate(AXSEED); pg4.goto(APP)
    pg4.wait_for_timeout(700)
    pg4.evaluate("() => switchTab('dash')")
    pg4.wait_for_timeout(700)
    for width in (1280, 402):
        *a, y = axes(pg4, width)
        # Årssammenligning (2026-09-28, his go): its x is the week of the YEAR, one axis for every
        # year's line, so the title is «uke» alone — the legend names the years. Read with .get():
        # a missing chart must fail these checks, not crash the suite before the rest run (#31).
        check(f"{width} px — Årssammenligning: control, both years drawn and labelled",
              (y.get('sets', 0) >= 2, len(y.get('ticks', [])) >= 5), (True, True))
        check(f"{width} px — Årssammenligning: flat, with «uke» once under the axis",
              (y.get('rot'), y.get('title')), (0, 'uke'))
        check(f"{width} px — Årssammenligning: each tick is its column's week, zero-padded",
              [(t['l'], y['labels'][t['v']]) for t in y.get('ticks', [])
               if f"Uke {t['l']}" != y['labels'][t['v']]][:2], [])
        check(f"{width} px — control: all eight weekly charts rendered, 26 weeks each",
              [(x['n'], len(x.get('labels', []))) for x in a], [(n, 26) for n in WEEKLY])
        check(f"{width} px — every week axis is flat", {x['n']: x['rot'] for x in a if x['rot']}, {})
        check(f"{width} px — each tick is the week of the bar above it, zero-padded",
              {x['n']: misplaced(x)[:2] for x in a if misplaced(x)}, {})
        check(f"{width} px — the unit and both years said once, under the axis",
              {x['n']: x['title'] for x in a if x['title'] != "uke · 2025–26"}, {})
        if width == 1280:
            check("1280 px — every week is named", {x['n']: len(x['ticks']) for x in a if len(x['ticks']) < 26}, {})
            wd = next(x for x in a if x['n'] == 'weeklyDist')
            check("...and New Year reads 52 → 01", ' 52 01 ' in f" {' '.join(t['l'] for t in wd['ticks'])} ", True)
        else:
            check("402 px — at least every third week is named",
                  {x['n']: len(x['ticks']) for x in a if len(x['ticks']) * 3 < 26}, {})
    # The bar is found by its raw week key, never by the display label under test (falsification: a
    # lookup through Pulssoner's own labels crashed before the tooltip was read). Every weekly chart
    # holds the same 26 weeks here, so one index serves both.
    i = pg4.evaluate("() => Charts.load.data._rawLabels.indexOf('2026-01')")
    check("control: week 2026-01 is in view", i >= 0, True)
    check("the tooltip keeps the full week: Pulssoner (its default title)", pg4.evaluate(TIP, ['zones', i]), ["Uke 01 '26"])
    check("...and Ukentlig distanse (its own title)", pg4.evaluate(TIP, ['weeklyDist', i]), ["Uke 01 '26"])
    check("...and Årssammenligning names its first column «Uke 01», padded like the rest",
          pg4.evaluate(TIP, ['yearComp', 0]), ["Uke 01"])
    pg4.set_viewport_size({"width": 1280, "height": 900})
    pg4.wait_for_function("() => Charts.weeklyDist.width > 1000", timeout=6000)
    pg4.click("#distToggleMaaned")
    pg4.wait_for_timeout(400)
    m = pg4.evaluate(AXES, ['weeklyDist'])[0]
    check("Måned: the ticks are the month names alone",
          [t['l'] for t in m['ticks']], ['Okt', 'Nov', 'Des', 'Jan', 'Feb', 'Mar', 'Apr'])
    check("...flat, with the years once under the axis", (m['rot'], m['title']), (0, '2025–26'))
    pg4.close()

    check("no page errors", errs, [])
    b.close()

print(f"\n{passed}/{passed + failed} passed" + (f"  ({failed} FAILED)" if failed else ""))
sys.exit(1 if failed else 0)
