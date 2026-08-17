"""Verify the "Denne uken" strip + Ukentlig oversikt highlight.  (2026-08-05)

Standalone — NOT part of run_all.py, which is the fast no-browser gate. Run directly:
    python tests/test_weeknow.py           (needs Playwright + WebKit)

Why this exists rather than a port: the whole feature is DOM rendering, and its one real
correctness rule — compare against the SAME POINT last week, not last week's total — is a
date-arithmetic claim you cannot check by reading the code. The fixture deliberately gives
last week 4 km by today's weekday but 24 km in total, so the naive comparison and the correct
one disagree in sign.

No local data file exists (see memory reference-mobile-repro) — sessions are synthesised in-page.

THE CLOCK IS PINNED to a Wednesday (see FREEZE below). It used to date sessions relative to the
real today and claim that made it date-independent; it did not. The fixture puts last week's big
run on day 5, so from Saturday onward "the same point last week" legitimately includes it and the
scenario the test was built to check silently stopped existing — discovered 2026-08-08, a Saturday.
Relative dating is not the same as determinism: if a fixture depends on where you are in the week,
freeze the week.
"""
import json, pathlib, sys, tempfile
sys.stdout.reconfigure(encoding='utf-8')   # arrows/æøå in the assertions
from playwright.sync_api import sync_playwright

# Relative to this file, not the repo checkout path — CI clones somewhere else entirely.
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


# Build a session set in-page: N days ago -> a run. Distances chosen so the partial-week
# comparison and the full-week comparison give DIFFERENT answers (that's the whole point of
# the same-point-last-week rule).
SEED = """
(cfg) => {
  const dayMs = 86400000;
  const iso = d => new Date(d).toISOString().slice(0,10);
  const today = new Date(); today.setHours(12,0,0,0);
  // Monday-based index of today inside its week
  const idx = (today.getDay() + 6) % 7;
  const mkDate = (weeksBack, dayInWeek) =>
    iso(new Date(today.getTime() - (idx - dayInWeek) * dayMs - weeksBack * 7 * dayMs));
  const S = (dato, km, secs, tempo) => ({
    id: 'x' + dato + km, dato, uke: '', oktnavn: 'Test', okttype: 'Easy',
    treningsplan: 'Runna', varighet: secs, distanse: km, tempo, lopetype: 'utendors',
    'l\\u00f8petype': 'utendors', soner: [0,0,0,0,0]
  });
  const sessions = [];
  // THIS week: one run on Monday (day 0) = 5 km
  sessions.push(S(mkDate(0, 0), 5, 1800, 360));
  // LAST week: 4 km on Monday, then 20 km later in the week (day 5 = Saturday).
  // Same-point comparison (Mon..today) sees only the 4 km -> this week is UP.
  // Naive full-week comparison would see 24 km -> this week would look DOWN.
  sessions.push(S(mkDate(1, 0), 4, 1500, 375));
  sessions.push(S(mkDate(1, 5), 20, 7200, 360));
  const data = { sessions, shoes: [], goals: {}, events: cfg.events || [],
                 settings: { zones: [] }, lastUpdated: new Date().toISOString() };
  localStorage.setItem('lpl_cache', JSON.stringify(data));
  return { idx, monday: mkDate(0,0) };
}
"""


# Pin "now" to Wednesday 2026-08-05 12:00 local, before any app code runs. Everything downstream —
# localISODate(), absWeekNum(), the day-index arithmetic — then sees a fixed midweek day, so the
# partial-week fixture means the same thing whenever the suite is run.
FREEZE = """
(() => {
  const RealDate = Date;
  const fixed = new RealDate(2026, 7, 5, 12, 0, 0).getTime();   // month is 0-based: 7 = August
  function FakeDate(...a) { return a.length ? new RealDate(...a) : new RealDate(fixed); }
  FakeDate.prototype = RealDate.prototype;
  FakeDate.now = () => fixed;
  FakeDate.parse = RealDate.parse;
  FakeDate.UTC = RealDate.UTC;
  window.Date = FakeDate;
})();
"""


def boot(page, events=None):
    page.add_init_script(FREEZE)
    page.goto(APP)
    info = page.evaluate(SEED, {"events": events or []})
    page.goto(APP)
    page.evaluate("() => switchTab('dash')")
    page.wait_for_timeout(400)
    return info


with sync_playwright() as p:
    b = p.webkit.launch()

    # ---------------------------------------------------------------- 1. core
    print("== strip: partial-week comparison ==")
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    info = boot(pg)
    print(f"  (today is day {info['idx']} of the week, Monday=0)")

    strip = pg.locator("#weekNowCard")
    check("strip visible", strip.is_visible(), True)
    txt = strip.inner_text()
    check("shows this week's distance", "5.0 km" in txt, True)
    tiles = pg.locator("#weekNowCard .insight-item .i-val").all_inner_texts()
    # Økter is dropped when its count matches last week — see sessionsMoved. In this fixture it
    # does match (1 vs 1), so three tiles is the correct shape.
    check("three tiles when the session count did not move", len(tiles), 3)
    check("økter tile absent", "økter" in strip.inner_text() or "økt" in strip.inner_text(), False)
    # The decisive one: 5 km this week vs 4 km at the SAME POINT last week -> UP,
    # even though last week finished on 24 km.
    # Distance: 5 km this week vs 4 km at the SAME POINT last week -> up, even though last week
    # finished on 24 km. This is the assertion the whole partial-week rule exists for.
    check("distance delta is up", "wk-up" in pg.locator("#weekNowCard .insight-item").nth(0).inner_html(), True)
    check("distance delta keeps its decimal", "+1.0 km" in txt, True)
    check("names the comparison basis", "samme tid forrige uke" in txt, True)
    check("shows last week's same-point figure", "fra 4.0 km" in txt, True)
    # The footer states the basis only — repeating last week's distance/count there would print the
    # same two figures twice now that the tiles carry their own.
    check("footer does not repeat the figures",
          "samme tid forrige uke" in txt and "· 1 økt)" not in txt, True)
    check("no red arrow anywhere", pg.locator("#weekNowCard .wk-down").count(), 0)
    check("no page errors", errors, [])

    print("== every tile carries its own delta ==")
    # this week: 1 run / 5 km / 1800 s / 360 s-per-km
    # last week to date: 1 run / 4 km / 1500 s / 375 s-per-km
    deltas = [t.inner_text() for t in pg.locator("#weekNowCard .wk-tile-delta").all()]
    check("three deltas", len(deltas), 3)
    # Each delta carries last week's figure for that metric — "+14:59" is unreadable without it, and
    # for tid/tempo the baseline appears nowhere else on the card.
    check("distanse", deltas[0], "▲ +1.0 km\nfra 4.0 km")
    # Unchanged is a CSS-drawn equals, so it carries no text at all.
    check("every remaining tile carries a baseline", pg.locator("#weekNowCard .wk-was").count(), 3)
    # "+05:00", not "+5:00": secsToHmsShort only strips a leading "0:" hour part, so minutes keep
    # their zero. Shared with the splits block ("fra 00:02") — consistency beats a one-off formatter.
    check("tid", deltas[1], "▲ +05:00\nfra 0:25:00")
    # Pace improved 375 -> 360 s/km. The NUMBER fell, so the arrow points down, but it is an
    # improvement, so it must be worded "raskere" and coloured green — never red.
    check("tempo says raskere", deltas[2], "▼ 15 s raskere\nfra 6:15 /km")
    check("tempo delta is green not red",
          "wk-up" in pg.locator("#weekNowCard .insight-item").nth(2).inner_html(), True)

    # ---------------------------------------------------------------- 2. table highlight
    print("== Ukentlig oversikt highlight ==")
    check("current week row highlighted", pg.locator("tr.wk-current").count(), 1)
    check("tag says Denne uken", pg.locator("tr.wk-current .wk-current-tag").inner_text(), "Denne uken")
    check("highlighted row is the first row",
          pg.locator("#weeklyBody tr").first.get_attribute("class"), "wk-current")

    # The invariant: strip figures == the table's current-week row (filters cleared)
    row = pg.locator("tr.wk-current td").all_inner_texts()
    check("table row distance matches the strip", row[2], "5.0 km")
    check("table row session count matches the strip", row[1], "1")

    print("== Maaned toggle moves the highlight ==")
    pg.locator("#overviewToggleMaaned").click()
    pg.wait_for_timeout(200)
    check("tag follows the toggle", pg.locator("tr.wk-current .wk-current-tag").inner_text(), "Denne måneden")
    pg.locator("#overviewToggleWeek").click()
    pg.wait_for_timeout(200)

    # ---------------------------------------------------------------- 3. filters ignored
    print("== strip ignores the dashboard filters ==")
    pg.select_option("#dfType", "Tempo")          # no Tempo sessions exist at all
    pg.wait_for_timeout(300)
    check("strip still reports the week", "5.0 km" in pg.locator("#weekNowCard").inner_text(), True)
    check("table row is gone (it DOES follow filters)", pg.locator("tr.wk-current").count(), 0)
    pg.select_option("#dfType", "")
    pg.wait_for_timeout(300)

    # ---------------------------------------------------------------- 4. pace unit
    print("== snitt tempo follows the km/t toggle ==")
    check("min/km by default", "/km" in pg.locator("#weekNowCard").inner_text(), True)
    pg.locator('input[name="dfPaceUnit"][value="kmh"]').check()
    pg.wait_for_timeout(300)
    check("switches to km/t", "km/t" in pg.locator("#weekNowCard").inner_text(), True)
    pg.locator('input[name="dfPaceUnit"][value="pace"]').check()
    pg.wait_for_timeout(300)

    # ---------------------------------------------------------------- 5. click-through
    print("== click opens the week drill-down ==")
    pg.locator("#weekNowCard").click()
    pg.wait_for_timeout(400)
    check("detail panel opened", pg.locator("#detailModal").is_visible(), True)
    check("panel is the current week",
          "Uke" in pg.locator("#detailTitle").inner_text(), True)
    pg.keyboard.press("Escape")
    pg.close()

    # ---------------------------------------------------------------- 6. deload context
    print("== deload week: neutral, not red ==")
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    # Make THIS week genuinely lower than last week's same point, then cover it with a deload.
    DOWN = """
    () => {
      const d = JSON.parse(localStorage.getItem('lpl_cache'));
      // drop this week's run to 1 km so the delta is negative
      const dayMs = 86400000, iso = x => new Date(x).toISOString().slice(0,10);
      const t = new Date(); t.setHours(12,0,0,0);
      const idx = (t.getDay()+6)%7;
      const mon = iso(new Date(t.getTime() - idx*dayMs));
      d.sessions.filter(s => s.dato === mon).forEach(s => { s.distanse = 1; });
      localStorage.setItem('lpl_cache', JSON.stringify(d));
      return mon;
    }
    """
    boot(pg)
    mon = pg.evaluate(DOWN)
    pg.goto(APP); pg.evaluate("() => switchTab('dash')"); pg.wait_for_timeout(400)
    check("without an event a drop is red", pg.locator("#weekNowCard .wk-down").count(), 1)

    # now add a deload covering this week
    pg.evaluate("""
    (mon) => {
      const d = JSON.parse(localStorage.getItem('lpl_cache'));
      d.events = [{ id:'e1', type:'deload', title:'Deload', date: mon, endDate: mon }];
      localStorage.setItem('lpl_cache', JSON.stringify(d));
    }""", mon)
    pg.goto(APP); pg.evaluate("() => switchTab('dash')"); pg.wait_for_timeout(400)
    t2 = pg.locator("#weekNowCard").inner_text()
    check("deload turns every verdict neutral", pg.locator("#weekNowCard .wk-down").count(), 0)
    check("no green verdicts either", pg.locator("#weekNowCard .wk-up").count(), 0)
    check("neutral class used throughout", pg.locator("#weekNowCard .wk-flat").count() >= 1, True)
    check("names the reason", "Deload" in t2, True)
    check("says lower is planned", "lavere er planlagt" in t2, True)
    check("the number itself still shows", "km" in t2, True)
    pg.close()

    # ---------------------------------------------------------------- 7. empty week
    print("== no runs yet this week ==")
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    boot(pg)
    pg.evaluate("""
    () => {
      const d = JSON.parse(localStorage.getItem('lpl_cache'));
      // Compare DATE STRINGS: s.dato parses as UTC midnight while a local Date is noon, so a
      // timestamp comparison keeps Monday's run and the fixture silently fails to be empty.
      const dayMs = 86400000, iso = x => new Date(x).toISOString().slice(0,10);
      const t = new Date(); t.setHours(12,0,0,0);
      const mon = iso(new Date(t.getTime() - ((t.getDay()+6)%7)*dayMs));
      d.sessions = d.sessions.filter(s => s.dato < mon);
      localStorage.setItem('lpl_cache', JSON.stringify(d));
    }""")
    pg.goto(APP); pg.evaluate("() => switchTab('dash')"); pg.wait_for_timeout(400)
    e = pg.locator("#weekNowCard").inner_text()
    check("strip still shows", pg.locator("#weekNowCard").is_visible(), True)
    check("says nothing logged yet", "Ingen økter ennå" in e, True)
    check("no zero-filled tiles", "0.0 km" in e, False)
    check("no row to highlight", pg.locator("tr.wk-current").count(), 0)
    pg.close()

    # ---------------------------------------------------------------- 7b. today's planned session
    print("== 'I dag' line from an imported plan ==")
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    perr = []
    pg.on("pageerror", lambda e: perr.append(str(e)))
    boot(pg)

    def with_plan(planned, events_extra=None, sessions_extra=None):
        """Re-seed with a Plan event covering today plus the given planned sessions."""
        pg.evaluate("""(cfg) => {
          const d = JSON.parse(localStorage.getItem('lpl_cache'));
          const iso = x => new Date(x).toISOString().slice(0,10);
          const t = new Date(); t.setHours(12,0,0,0);
          const today = iso(t);
          const start = iso(new Date(t.getTime() - 20*86400000));
          const end   = iso(new Date(t.getTime() + 20*86400000));
          d.events = [{ id:'p1', type:'plan', title:'Runna 5K', date:start, endDate:end }]
                     .concat(cfg.eventsExtra || []);
          d.plannedSessions = (cfg.planned || []).map((p, i) => ({
            id:'pl'+i, date: p.today ? today : iso(new Date(t.getTime() + 3*86400000)),
            okttype: p.okttype, distance: p.distance, title: p.title || '' }));
          // Idempotent: drop any run a PREVIOUS with_plan() added before adding this call's. Without
          // this they accumulate, and a leftover matching run makes the excused case report 'done'
          // instead (matched beats excused, by design).
          d.sessions = d.sessions.filter(s => !String(s.id).startsWith('ex'));
          if (cfg.sessionsExtra) d.sessions = d.sessions.concat(cfg.sessionsExtra.map((s, i) => ({
            id:'ex'+i, dato: today, uke:'', oktnavn:'Logged', okttype: s.okttype,
            treningsplan:'Runna', varighet: s.varighet, distanse: s.distanse,
            tempo: 360, soner:[0,0,0,0,0] })));
          localStorage.setItem('lpl_cache', JSON.stringify(d));
        }""", {"planned": planned, "eventsExtra": events_extra or [], "sessionsExtra": sessions_extra or []})
        pg.goto(APP); pg.evaluate("() => switchTab('dash')"); pg.wait_for_timeout(400)

    # nothing planned today -> the line must be absent, NOT "Hviledag"
    with_plan([{"today": False, "okttype": "Easy", "distance": 5}])
    check("no line when nothing is planned today", pg.locator(".wk-now-plan").count(), 0)
    check("never claims a rest day", "Hviledag" in pg.locator("#weekNowCard").inner_text(), False)

    # planned and not yet logged
    with_plan([{"today": True, "okttype": "Easy", "distance": 5}])
    check("line appears", pg.locator(".wk-now-plan").count(), 1)
    check("names type and distance", pg.locator(".wk-now-plan").inner_text(), "📋 I dag: Easy · 5 km")

    # a flavoured Runna name is appended; a generic one is not (plannedTitle strips it)
    with_plan([{"today": True, "okttype": "Intervaller", "distance": 8, "title": "Rolling 300s"}])
    check("flavoured title shown", "Rolling 300s" in pg.locator(".wk-now-plan").inner_text(), True)
    with_plan([{"today": True, "okttype": "Easy", "distance": 5, "title": "Easy Run"}])
    check("generic title not repeated", pg.locator(".wk-now-plan").inner_text(), "📋 I dag: Easy · 5 km")

    # logged today -> the same line answers "have I done it"
    with_plan([{"today": True, "okttype": "Easy", "distance": 5}],
              sessions_extra=[{"okttype": "Easy", "distance": 5.0, "varighet": 1800}])
    txt2 = pg.locator(".wk-now-plan").inner_text()
    check("done shows a tick", txt2.startswith("✓"), True)
    check("done is styled apart", pg.locator(".wk-now-plan-done").count(), 1)

    # excused by a registered Sykdom -> suppressed, same as the streak nudge
    with_plan([{"today": True, "okttype": "Easy", "distance": 5}],
              events_extra=[{"id": "ill", "type": "illness", "title": "Syk"}])
    pg.evaluate("""() => {
      const d = JSON.parse(localStorage.getItem('lpl_cache'));
      const t = new Date(); t.setHours(12,0,0,0);
      const iso = x => new Date(x).toISOString().slice(0,10);
      d.events = d.events.map(e => e.type === 'illness' ? { ...e, date: iso(t), endDate: iso(t) } : e);
      localStorage.setItem('lpl_cache', JSON.stringify(d));
    }""")
    pg.goto(APP); pg.evaluate("() => switchTab('dash')"); pg.wait_for_timeout(400)
    check("suppressed while excused", pg.locator(".wk-now-plan").count(), 0)
    check("no page errors", perr, [])
    pg.close()

    # ---------------------------------------------------------------- 8. mobile 402
    print("== mobile 402px ==")
    pg = b.new_page(viewport={"width": 402, "height": 900})
    merr = []
    pg.on("pageerror", lambda e: merr.append(str(e)))
    boot(pg)
    over = pg.evaluate("""
    () => {
      const card = document.getElementById('weekNowCard');
      const bad = [];
      // check every leaf span, not just the row — textContent lies through an ellipsis
      card.querySelectorAll('div,span').forEach(el => {
        if (el.scrollWidth > el.clientWidth + 1 && el.clientWidth > 0) bad.push(el.className + '|' + el.textContent.trim().slice(0,30));
      });
      return { bad, cardRight: card.getBoundingClientRect().right, docW: document.documentElement.clientWidth };
    }""")
    check("no clipped child in the strip", over["bad"], [])
    check("strip within viewport", over["cardRight"] <= over["docW"] + 1, True)
    check("no mobile page errors", merr, [])
    # Debug aid only — nothing above asserts on it. Temp dir so a capture can never land in the
    # repo, where the blanket *.png ignore is the only thing standing between it and a commit.
    pg.screenshot(path=str(pathlib.Path(tempfile.gettempdir()) / "weeknow_402.png"),
                  clip={"x": 0, "y": 0, "width": 402, "height": 520})
    pg.close()

    # ── The empty week shows the PLAN instead of a sentence that says nothing ────────────────
    #
    # Requires history: with zero sessions ever, renderDashboard shows its fresh-install empty
    # state and hides this card entirely, so a fixture with no sessions at all would assert
    # against a hidden element and pass for the wrong reason.
    print("== empty week -> planlagt denne uken ==")

    # Monday 2026-08-10, the week the feature was built for. Absolute dates, so the block window
    # and the planned days cannot drift with the real calendar.
    EMPTY_WEEK = """
    (cfg) => {
      const prior = { id:'old', dato:'2026-08-05', uke:'2026-32', oktnavn:'x', okttype:'Easy',
                      treningsplan:'Runna', distanse:6, varighet:2100, tempo:350, soner:[0,0,0,0,0] };
      localStorage.setItem('lpl_cache', JSON.stringify({
        sessions: [prior].concat(cfg.extra || []),
        shoes: [], goals: {}, settings: { zones: [] },
        events: cfg.events, plannedSessions: cfg.planned, lastUpdated: '' }));
    }"""
    BLOCK = [{"id": "p", "type": "plan", "title": "Runna 10K", "date": "2026-08-03", "endDate": "2026-10-01"}]
    WEEK_PLAN = [
        {"id": "a", "date": "2026-08-10", "okttype": "Easy",  "distance": 4.5, "title": ""},
        {"id": "b", "date": "2026-08-12", "okttype": "Tempo", "distance": 7,   "title": ""},
        {"id": "d", "date": "2026-08-16", "okttype": "Long",  "distance": 14,  "title": ""},
        {"id": "e", "date": "2026-08-20", "okttype": "Tempo", "distance": 8,   "title": ""},  # next week
    ]
    def freeze_on(day):
        return """
        (() => { const R = Date; const fixed = new R(2026, 7, %d, 12, 0, 0).getTime();
          function F(...a){ return a.length ? new R(...a) : new R(fixed); }
          F.prototype = R.prototype; F.now = () => fixed; F.parse = R.parse; F.UTC = R.UTC;
          window.Date = F; })();""" % day

    # okttype matters: matchPlannedSessions claims pairs best-score-first, so which planned session a
    # run credits depends on its type, not only its date. A fixture that leaves it at Easy cannot
    # produce an overdue session at all — the run just slides onto the earlier Easy slot.
    def logged(n, date, km, secs, okttype="Easy"):
        return {"id": "s%d" % n, "dato": date, "uke": "2026-33", "oktnavn": "x", "okttype": okttype,
                "treningsplan": "Runna", "distanse": km, "varighet": secs,
                "tempo": round(secs / km), "soner": [0, 0, 0, 0, 0]}

    def week_card(events, planned, width=1280, day=10, extra=None):
        p = b.new_page(viewport={"width": width, "height": 900})
        errs = []
        p.on("pageerror", lambda e: errs.append(str(e)))
        p.add_init_script(freeze_on(day))
        p.goto(APP)
        p.evaluate(EMPTY_WEEK, {"events": events, "planned": planned, "extra": extra or []})
        p.goto(APP)
        p.evaluate("() => switchTab('dash')")
        p.wait_for_timeout(500)
        txt = " ".join(p.inner_text("#weekNowCard").split())
        clipped = p.evaluate("""() => { const bad = [];
            document.querySelectorAll('#weekNowCard div,#weekNowCard span').forEach(el => {
              if (el.scrollWidth > el.clientWidth + 1 && el.clientWidth > 0) bad.push(el.className); });
            return bad; }""")
        p.close()
        return txt, errs, clipped

    txt, errs, _ = week_card(BLOCK, WEEK_PLAN)
    check("lead line present", "PLANLAGT DENNE UKEN" in txt, True)
    check("count starts at nothing done", "· 0/3" in txt, True)
    check("monday session listed", "Man Easy · 4.5 km" in txt, True)
    check("wednesday session listed", "Ons Tempo · 7 km" in txt, True)
    check("sunday session listed", "Søn Long · 14 km" in txt, True)
    # THE SCOPING RULE: next week's session must not leak in. Same absWeekNum the rest of the card
    # uses — a second way of deciding "this week" is how two surfaces start disagreeing.
    check("next week's session excluded", "8 km" in txt, False)
    check("old empty sentence gone", "Ingen økter ennå" in txt, False)
    check("no page errors", errs, [])

    # No plan at all, and a plan with nothing this week, BOTH fall back to the old sentence.
    # Absence of a plan is not a rest week — only runs are imported from the .ics, so it must not
    # claim one. Same reason plannedToday() never says "Hviledag".
    txt, _, _ = week_card([], WEEK_PLAN)
    check("no plan event -> old sentence", "Ingen økter ennå denne uken." in txt, True)
    check("...and no plan list", "PLANLAGT" in txt, False)

    txt, _, _ = week_card(BLOCK, [{"id": "z", "date": "2026-09-01", "okttype": "Easy", "distance": 5, "title": ""}])
    check("block active but empty week -> old sentence", "Ingen økter ennå denne uken." in txt, True)
    check("...still no rest-day claim", "Hviledag" in txt, False)

    # Excused (Syk/Ferie) sessions are left out, matching the "I dag" line's rule.
    SICK = BLOCK + [{"id": "s", "type": "illness", "title": "Syk", "date": "2026-08-11", "endDate": "2026-08-13"}]
    txt, _, _ = week_card(SICK, WEEK_PLAN)
    check("excused session hidden", "Ons Tempo · 7 km" in txt, False)
    check("...but the rest still shown", "Man Easy · 4.5 km" in txt, True)

    txt, _, clipped = week_card(BLOCK, WEEK_PLAN, width=402)
    check("plan list unclipped at 402px", clipped, [])
    check("...and still listed", "Søn Long · 14 km" in txt, True)

    # ── The WHOLE week, all week long, under the stats ──────────────────────────────────────
    #
    # The heading says "Planlagt denne uken", so the list is the week — not what is left of it. It
    # used to filter to pending once any run existed, which meant a done session vanished and
    # mid-week you could not tell whether the week started with three sessions or one.
    print("== full week plan under the stats ==")
    MON, WED = logged(1, "2026-08-10", 4.5, 1600), logged(2, "2026-08-12", 5, 1800)

    txt, errs, _ = week_card(BLOCK, WEEK_PLAN, day=10, extra=[MON])
    check("one heading in both layouts", "PLANLAGT DENNE UKEN" in txt, True)
    check("...never the old 'igjen'", "IGJEN" in txt, False)
    check("...with the stats alongside it", "4.5 km" in txt and "distanse" in txt, True)
    check("done session STAYS, ticked", "✓ Man Easy · 4.5 km" in txt, True)
    check("what is ahead stays, open", "○ Ons Tempo · 7 km" in txt, True)
    check("count reads done over planned", "· 1/3" in txt, True)
    check("no page errors", errs, [])

    # Today stays findable THROUGH its state class. The accent day name is the only marker left on
    # today's row — the bold moved to the header line — so if a state class ever outranks it, the
    # locator disappears silently and every row looks alike. Monday here is both today and done.
    p = b.new_page(viewport={"width": 1280, "height": 900})
    p.add_init_script(freeze_on(10))
    p.goto(APP)
    p.evaluate(EMPTY_WEEK, {"events": BLOCK, "planned": WEEK_PLAN, "extra": [MON]})
    p.goto(APP)
    p.evaluate("() => switchTab('dash')")
    p.wait_for_timeout(500)
    style = p.evaluate("""() => {
        const it = document.querySelector('.wk-plan-item.wk-plan-today');
        const cs = getComputedStyle(it), day = getComputedStyle(it.querySelector('.wk-plan-day'));
        return { item: cs.color, weight: cs.fontWeight, day: day.color }; }""")
    p.close()
    check("today's day name is accent, not the state colour", style["day"], "rgb(108, 143, 255)")
    check("...while the row itself carries the done green", style["item"], "rgb(76, 175, 135)")
    check("...and the row is no longer bold", int(style["weight"]) < 600, True)

    # Mid-week the count is the whole point: it cannot be read off a list that has dropped its
    # finished rows.
    txt, _, _ = week_card(BLOCK, WEEK_PLAN, day=14, extra=[MON, WED])
    check("both finished sessions still listed", txt.count("✓"), 2)
    check("...and the count follows", "· 2/3" in txt, True)
    check("...with the last one still ahead", "○ Søn Long · 14 km" in txt, True)

    # A finished week does NOT disappear. That standing height is the accepted cost of the heading
    # meaning what it says — it reads 3/3 with nothing open and nothing missed.
    txt, _, _ = week_card(BLOCK, WEEK_PLAN[:3], day=16,
                          extra=[MON, WED, logged(3, "2026-08-16", 14, 4900, "Long")])
    check("finished week still shown", "PLANLAGT DENNE UKEN" in txt, True)
    check("...reading 3/3", "· 3/3" in txt, True)
    check("...nothing open or missed left", txt.count("○") + txt.count("✗"), 0)

    # A MISSED session is shown, not dropped. Once the list claims to be the week, absence would read
    # as "never planned" — the one thing the old shrinking list could not get wrong, and the reason
    # this card now makes an adherence judgement it used to leave to the week drill-down.
    # The Wednesday run is a TEMPO here so it credits Wednesday's planned Tempo; as an Easy it would
    # score better against Monday's Easy and leave nothing overdue at all.
    txt, _, _ = week_card(BLOCK, WEEK_PLAN, day=12, extra=[logged(4, "2026-08-12", 7, 2400, "Tempo")])
    check("missed monday is listed", "✗ Man Easy · 4.5 km" in txt, True)
    check("...not counted as done", "· 1/3" in txt, True)
    check("...while today and later still are", "Søn Long · 14 km" in txt, True)

    # Excused leaves the DENOMINATOR too — numerator and denominator come off the same filtered rows,
    # so the count can never divide by a session the card refuses to show.
    txt, _, _ = week_card(SICK, WEEK_PLAN, day=12, extra=[MON])
    check("excused session stays hidden", "Ons Tempo" in txt, False)
    check("...and out of the count", "· 1/2" in txt, True)

    b.close()

print(f"\n{passed}/{passed+failed} passed" + ("" if not failed else f"  ({failed} FAILED)"))
sys.exit(1 if failed else 0)
