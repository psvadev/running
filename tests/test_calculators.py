"""Verktøy tab — finish time, target pace and the interval calculator.  (2026-08-09)

Standalone — NOT part of run_all.py, which is the fast no-browser gate. Run directly:
    python tests/test_calculators.py      (needs Playwright + WebKit)

Why a suite and not a port: all three are form state and DOM. No Python port can reach them.

THE DESIGN RULE THESE EXIST TO PROTECT: the Verktøy cards read NOTHING from Store. They must answer
for paces never run — a plan target, someone else's race, a goal you are not yet fit for. That rule
is a comment in the source and therefore rots; here it is executable. The strongest form is not
"works with no data" but "produces byte-identical output with and without sessions", which is what
the Store-free section asserts.

The anchors are the user's own worked examples, hand-computable end to end:
    10 km @ 6:15/km  -> 1:02:30, 9.6 km/t
    5 km in 29:30    -> 5:54/km, 10.2 km/t
    6 x 400 m @ 5:30 -> 2:12 per drag, 2.4 km, 13:12 arbeid, 7:30 pause (FIVE), 20:42 blokk

No local data file exists (see memory reference-mobile-repro) — sessions are synthesised in-page.
"""
import pathlib, sys
sys.stdout.reconfigure(encoding='utf-8')   # æøå + the emoji in the tab label
from playwright.sync_api import sync_playwright

# Relative to this file, not the repo checkout path — CI clones somewhere else entirely.
APP = (pathlib.Path(__file__).resolve().parent.parent / "puls.html").as_uri()
passed = failed = 0

# Two real sessions. Used ONLY to prove the tools ignore them.
SEED = """() => {
  localStorage.setItem('lpl_cache', JSON.stringify({
    sessions: [
      { id:'s1', dato:'2026-08-01', okttype:'Easy', distanse:5,  varighet:1800, lopetype:'treadmill' },
      { id:'s2', dato:'2026-08-03', okttype:'Long', distanse:15, varighet:5400, lopetype:'utendors' }
    ],
    shoes: [], goals: {}, settings: { zones: [] }, events: [], plannedSessions: [],
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


def boot(pg, seed=False):
    pg.goto(APP)
    if seed:
        pg.evaluate(SEED)
        pg.goto(APP)
    pg.evaluate("() => switchTab('tools')")
    pg.wait_for_timeout(400)


def txt(pg, sel):
    return " ".join(pg.inner_text(sel).split())


def fill(pg, sel, val):
    pg.fill(sel, val)
    pg.wait_for_timeout(80)


with sync_playwright() as b0:
    b = b0.webkit.launch()

    # ── 1. Sluttid ──────────────────────────────────────────────────────────────────────────
    print("== Sluttid ==")
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    boot(pg)

    check("tools panel exists", pg.locator("#panel-tools").is_visible(), True)

    fill(pg, "#tcDist", "10")
    fill(pg, "#tcPace", "6:15")
    check("10 km @ 6:15 -> finish", txt(pg, "#tcOut").startswith("1:02:30"), True)
    check("...and the speed", "9.6 km/t" in txt(pg, "#tcOut"), True)
    check("km/t field followed the pace", pg.input_value("#tcKmh"), "9.6")

    splits = txt(pg, "#tcSplits")
    check("split at 1 km",  "1 km 6:15" in splits, True)
    check("split at 5 km",  "5 km 31:15" in splits, True)
    check("split at 10 km", "10 km 1:02:30" in splits, True)
    check("no 11th split",  "11 km" in splits, False)

    # Marathon must not print 42 rows — every km to 10, then every 5, ending on the real distance.
    fill(pg, "#tcDist", "42.2")
    rows = pg.locator("#tcSplits .pc-row").count()
    check("marathon splits stay readable", rows, 17)
    check("last split is the real distance", "42.2 km" in txt(pg, "#tcSplits"), True)

    # A partial distance still terminates on itself rather than the last whole km.
    fill(pg, "#tcDist", "3.5")
    # 3.5 x 375 s = 1312.5 -> 1313 = 21:53. The half-second rounds up; do not "fix" this to 21:52.
    check("3.5 km ends on 3.5", txt(pg, "#tcSplits").endswith("3.5 km 21:53"), True)

    # ── 2. Måltempo ─────────────────────────────────────────────────────────────────────────
    print("== Måltempo ==")
    pg.click("#tcModes .tc-mode[data-mode='target']")
    pg.wait_for_timeout(120)
    check("distance survived the mode switch", pg.input_value("#tcDist"), "3.5")

    fill(pg, "#tcDist", "5")
    fill(pg, "#tcTime", "29:30")
    check("5 km in 29:30 -> pace", txt(pg, "#tcOut").startswith("5:54 /km"), True)
    check("...and the speed", "10.2 km/t" in txt(pg, "#tcOut"), True)
    check("goal chips bracket the value", txt(pg, "#tcGoalChips"), "Sub-32:30 Sub-30 Sub-27:30 Sub-25")

    pg.click("#tcGoalChips .tc-chip:nth-child(2)")     # Sub-30
    pg.wait_for_timeout(120)
    check("clicking a goal fills the time", pg.input_value("#tcTime"), "30:00")
    check("...and repaces", txt(pg, "#tcOut").startswith("6:00 /km"), True)

    # THE ROUND TRIP: distance + pace -> time, fed back as a target, returns the original pace.
    # This is the invariant; the anchors above are only examples of it.
    for dist, pace in [("10", "6:15"), ("21.1", "5:30"), ("5", "4:45")]:
        pg.click("#tcModes .tc-mode[data-mode='finish']")
        fill(pg, "#tcDist", dist)
        fill(pg, "#tcPace", pace)
        got_time = txt(pg, "#tcOut").split(" ")[0]
        pg.click("#tcModes .tc-mode[data-mode='target']")
        fill(pg, "#tcTime", got_time)
        check(f"round-trip {dist} km @ {pace}", txt(pg, "#tcOut").startswith(pace + " /km"), True)

    # Incomplete input shows a dash, never a number derived from nothing.
    fill(pg, "#tcTime", "")
    check("no target -> dash, not 0", txt(pg, "#tcOut").startswith("–"), True)
    check("splits hidden when incomplete", pg.locator("#tcSplitsWrap").is_visible(), False)

    # ── 3. Intervaller ──────────────────────────────────────────────────────────────────────
    print("== Intervaller ==")
    fill(pg, "#ivReps", "6")
    fill(pg, "#ivVal", "400")
    pg.select_option("#ivUnit", "m")
    fill(pg, "#ivPace", "5:30")
    fill(pg, "#ivRest", "90")
    pg.wait_for_timeout(120)

    hero = txt(pg, "#ivHero")
    check("hero names the speed", "Sett farten til 10.9 km/t" in hero, True)
    check("hero names the rep time", "Løp i 2:12" in hero, True)

    out = txt(pg, "#ivOut")
    check("per drag",        "2:12 PER DRAG" in out.upper(), True)
    check("rep length in m", "400 m" in out, True)
    check("work distance",   "2.4 km" in out, True)
    check("work time",       "13:12" in out, True)
    check("rest total",      "7:30" in out, True)
    check("FIVE pauses for six reps", "5 PAUSER" in out.upper(), True)
    check("block duration",  "20:42" in out, True)

    # THE TRAILING-RECOVERY INVARIANT: ticking the box adds exactly one recovery, no more.
    pg.check("#ivTrailRest")
    pg.wait_for_timeout(120)
    out2 = txt(pg, "#ivOut")
    check("six pauses when trailing", "6 PAUSER" in out2.upper(), True)
    check("block grew by exactly one rest", "22:12" in out2, True)   # 20:42 + 1:30
    pg.uncheck("#ivTrailRest")
    pg.wait_for_timeout(120)
    check("unticking restores", "20:42" in txt(pg, "#ivOut"), True)

    # Time-based inverts cleanly.
    fill(pg, "#ivReps", "5")
    fill(pg, "#ivVal", "3")
    pg.select_option("#ivUnit", "min")
    fill(pg, "#ivKmh", "10.5")
    pg.wait_for_timeout(120)
    check("time-based rep time", "Løp i 3:00" in txt(pg, "#ivHero"), True)
    check("time-based rep length", "525 m" in txt(pg, "#ivOut"), True)
    check("time-based work distance", "2.62 km" in txt(pg, "#ivOut"), True)
    check("four pauses for five reps", "4 PAUSER" in txt(pg, "#ivOut").upper(), True)

    # Recovery as DISTANCE: the block duration is unknowable without a recovery pace, so it must be
    # a dash with the reason attached — never a number invented from the work pace.
    pg.select_option("#ivRestUnit", "m")
    fill(pg, "#ivRest", "200")
    pg.wait_for_timeout(120)
    out3 = txt(pg, "#ivOut")
    check("recovery distance shown", "800 m" in out3, True)          # 4 pauses x 200 m
    check("block duration refuses to guess", "– HELE BLOKKA" in out3.upper(), True)
    check("...and says why", "KREVER PAUSETEMPO" in out3.upper(), True)

    # Incomplete input never renders a half-computed block.
    fill(pg, "#ivReps", "")
    check("empty state, not zeros", "Fyll inn" in txt(pg, "#ivHero"), True)
    check("no stats while incomplete", txt(pg, "#ivOut"), "")

    check("no page errors", errs, [])
    pg.close()

    # ── 4. Store-free — the design rule, made executable ────────────────────────────────────
    print("== reads nothing from Store ==")

    def snapshot(seed):
        p = b.new_page(viewport={"width": 1280, "height": 900})
        boot(p, seed=seed)
        p.fill("#tcDist", "10"); p.fill("#tcPace", "6:15")
        p.fill("#ivReps", "6");  p.fill("#ivVal", "400")
        p.fill("#ivPace", "5:30"); p.fill("#ivRest", "90")
        p.wait_for_timeout(200)
        s = (txt(p, "#tcOut"), txt(p, "#tcSplits"), txt(p, "#ivHero"), txt(p, "#ivOut"),
             txt(p, "#pcTable"))
        p.close()
        return s

    empty, seeded = snapshot(False), snapshot(True)
    check("output identical with and without sessions", empty, seeded)
    check("...and it was not simply blank", empty[0].startswith("1:02:30"), True)

    # ── 5. Decimal point, never a comma ─────────────────────────────────────────────────────
    print("== decimal point on output, either separator on input ==")
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    boot(pg)
    fill(pg, "#tcDist", "10")
    fill(pg, "#tcKmh", "9,6")                       # comma IN
    check("comma input accepted", pg.input_value("#tcPace"), "6:15")
    check("point out", pg.input_value("#tcKmh"), "9,6")   # untouched: handlers write only the other
    fill(pg, "#tcPace", "6:15")
    check("no comma in tcOut", "," in txt(pg, "#tcOut"), False)
    fill(pg, "#ivReps", "6"); fill(pg, "#ivVal", "400")
    fill(pg, "#ivPace", "5:30"); fill(pg, "#ivRest", "90")
    check("no comma in the interval hero", "," in txt(pg, "#ivHero"), False)
    pg.close()

    # ── 6. Mobile, 402 px ───────────────────────────────────────────────────────────────────
    print("== mobile 402px ==")
    pg = b.new_page(viewport={"width": 402, "height": 850})
    merr = []
    pg.on("pageerror", lambda e: merr.append(str(e)))
    boot(pg)
    fill(pg, "#tcDist", "42.2")
    fill(pg, "#tcPace", "6:15")
    fill(pg, "#ivReps", "6"); fill(pg, "#ivVal", "400")
    fill(pg, "#ivPace", "5:30"); fill(pg, "#ivRest", "90")
    over = pg.evaluate("""
    () => {
      const bad = [];
      document.querySelectorAll('#panel-tools div,#panel-tools span,#panel-tools button').forEach(el => {
        if (el.scrollWidth > el.clientWidth + 1 && el.clientWidth > 0) bad.push(el.className || el.id);
      });
      return { bad, docW: document.documentElement.clientWidth,
               bodyW: document.body.scrollWidth };
    }""")
    check("nothing clipped in the tools panel", over["bad"], [])
    check("page does not scroll sideways", over["bodyW"] <= over["docW"] + 1, True)
    # The 7th tab must not break the bar — it scrolls, it does not wrap or overflow the page.
    check("tab bar still scrolls", pg.evaluate(
        "() => { const t = document.querySelector('.tabs'); return t.scrollWidth > t.clientWidth; }"), True)
    check("no mobile page errors", merr, [])
    pg.close()

    b.close()

print(f"\n{passed}/{passed+failed} passed" + ("" if not failed else f"  ({failed} FAILED)"))
sys.exit(1 if failed else 0)
