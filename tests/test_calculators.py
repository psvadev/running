"""Verktøy tab — finish time, target pace, distance and the interval calculator.  (2026-08-09)

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
    35:00 @ 6:20/km  -> 5.53 km, 9.5 km/t
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

    # ── 3. Distanse ─────────────────────────────────────────────────────────────────────────
    # The third side of the same triangle: time + pace -> how far you get. Added 2026-08-26 after
    # "35 min at 6:20" had no home — you had to guess a distance in Sluttid and nudge it.
    print("== Distanse ==")
    pg.click("#tcModes .tc-mode[data-mode='dist']")
    pg.wait_for_timeout(150)

    # WHICH ROWS SHOW IS THE FEATURE, not decoration: the field you are solving for must not also be
    # typeable, or the card silently ignores half of what you entered.
    check("distance row hidden — it is the answer", pg.locator("#tcDistIn").is_visible(), False)
    check("pace/speed row shown", pg.locator("#tcFinishIn").is_visible(), True)
    check("time row shown", pg.locator("#tcTargetIn").is_visible(), True)
    # ⚠️ The two CHIP rows are asserted on computed `display`, not is_visible(). Both can be EMPTY —
    # renderGoalChips blanks its container whenever the inputs are incomplete — and an empty div has
    # no box, so is_visible() answers False no matter what display says. Falsified: a break that left
    # the goal chips on display:flex in this mode was caught by nothing until this became a style read.
    disp = lambda sel: pg.evaluate(f"() => getComputedStyle(document.querySelector('{sel}')).display")
    check("...and its presets with it", disp("#tcDistChips"), "none")
    check("goal chips hidden — they bracket a FINISH time", disp("#tcGoalChips"), "none")
    check("time is time spent, not a goal", txt(pg, "#tcTimeLabel"), "⌛ Tid")
    check("nothing entered -> dash", txt(pg, "#tcOut").startswith("–"), True)
    check("...naming the two fields THIS mode wants",
          "TID OG TEMPO" in txt(pg, "#tcOut"), True)

    fill(pg, "#tcTime", "35:00")
    fill(pg, "#tcPace", "6:20")
    check("35:00 @ 6:20 -> distance", txt(pg, "#tcOut").startswith("5.53 km"), True)
    check("...and the speed", "9.5 km/t" in txt(pg, "#tcOut"), True)
    # The split table closes the loop on itself: the last row must be the time you typed. If the
    # distance were wrong, this row would disagree with the input sitting right above it.
    check("last split lands exactly on the entered time",
          txt(pg, "#tcSplits").endswith("5.53 km 35:00"), True)
    check("splits still every km up to it", "5 km 31:40" in txt(pg, "#tcSplits"), True)

    # A whole number must not print as 10.00 km — same trailing-zero rule the split labels use.
    fill(pg, "#tcTime", "1:02:30")
    fill(pg, "#tcPace", "6:15")
    check("exact distance drops the decimals", txt(pg, "#tcOut").startswith("10 km "), True)

    # THE ROUND TRIP, third direction: distance + pace -> time, fed back with the same pace, returns
    # the original distance. Same invariant as the Måltempo round trip, rotated one side further.
    for dist, pace in [("10", "6:15"), ("21.1", "5:30"), ("5", "4:45")]:
        pg.click("#tcModes .tc-mode[data-mode='finish']")
        fill(pg, "#tcDist", dist)
        fill(pg, "#tcPace", pace)
        got_time = txt(pg, "#tcOut").split(" ")[0]
        pg.click("#tcModes .tc-mode[data-mode='dist']")
        fill(pg, "#tcTime", got_time)
        check(f"round-trip {got_time} @ {pace}", txt(pg, "#tcOut").startswith(dist + " km"), True)

    # Half the input is not an answer.
    fill(pg, "#tcTime", "")
    check("no time -> dash, not 0", txt(pg, "#tcOut").startswith("–"), True)
    check("splits hidden when incomplete", pg.locator("#tcSplitsWrap").is_visible(), False)

    # ⚠️ A derived distance must NOT be written back into the field. It would overwrite the race
    # distance you typed in the other two modes — which deliberately survives a mode switch — and a
    # hand-entry field holding a computed number has no honest provenance.
    pg.click("#tcModes .tc-mode[data-mode='finish']")
    fill(pg, "#tcDist", "12")
    pg.click("#tcModes .tc-mode[data-mode='dist']")
    fill(pg, "#tcTime", "35:00")
    fill(pg, "#tcPace", "6:20")
    check("the answer is 5.53 km", txt(pg, "#tcOut").startswith("5.53 km"), True)
    pg.click("#tcModes .tc-mode[data-mode='finish']")
    pg.wait_for_timeout(150)
    check("...but the typed 12 km is untouched", pg.input_value("#tcDist"), "12")

    # Exactly one mode is active at a time.
    for m in ["finish", "target", "dist"]:
        pg.click(f"#tcModes .tc-mode[data-mode='{m}']")
        pg.wait_for_timeout(100)
        check(f"only '{m}' is lit", pg.locator("#tcModes .tc-on").count(), 1)

    # ── 4. Intervaller ──────────────────────────────────────────────────────────────────────
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
    check("block duration refuses to guess", "– HELE BLOKKEN" in out3.upper(), True)
    check("...and says why", "KREVER PAUSETEMPO" in out3.upper(), True)

    # Incomplete input never renders a half-computed block.
    fill(pg, "#ivReps", "")
    check("empty state, not zeros", "Fyll inn" in txt(pg, "#ivHero"), True)
    check("no stats while incomplete", txt(pg, "#ivOut"), "")

    # Both unit groups stay visible and divided, never filtered — clicking across the divider is a
    # one-click mode switch, and filtering would hide the time-based mode entirely.
    pg.select_option("#ivUnit", "m")
    pg.wait_for_timeout(100)
    check("metre chips visible in metre mode", pg.locator("#ivValChips .tc-chip[data-unit='m']").count(), 6)
    check("minute chips ALSO visible in metre mode", pg.locator("#ivValChips .tc-chip[data-unit='min']").count(), 3)
    check("the two groups are divided", pg.locator("#ivValChips .tc-chip-sep").count(), 1)
    pg.click("#ivValChips .tc-chip[data-val='4'][data-unit='min']")
    pg.wait_for_timeout(120)
    check("clicking across the divider switches the unit", pg.input_value("#ivUnit"), "min")
    check("...and fills the value", pg.input_value("#ivVal"), "4")

    # The distance ladder: a pyramid holds ONE pace and varies the distance, so the belt setting never
    # changes and only the rep times are missing. Driven by the pace alone — it must appear before the
    # session is fully described, which is when you are still working out what to run.
    fill(pg, "#ivReps", "")
    fill(pg, "#ivVal", "")
    fill(pg, "#ivPace", "5:30")
    strip = txt(pg, "#ivStrip")
    check("strip renders from the pace alone", "200 m 1:06" in strip, True)
    for d, t in [("300 m", "1:39"), ("400 m", "2:12"), ("600 m", "3:18"),
                 ("800 m", "4:24"), ("1000 m", "5:30")]:
        check(f"ladder {d}", f"{d} {t}" in strip, True)
    # .ivs-lead is text-transform:uppercase, and inner_text returns the RENDERED text — so this
    # compares case-insensitively rather than against the source string.
    check("strip names the pace it used", "5:30 /km" in strip.lower(), True)
    fill(pg, "#ivPace", "")
    check("no pace -> no strip", pg.locator("#ivStrip").is_visible(), False)

    # A placeholder must not read as a value: the card once showed 6 / 5:30 / 90 while saying
    # "fyll inn", which is a contradiction. Weight is what separates them.
    weights = pg.evaluate("""() => {
      const s = getComputedStyle(document.getElementById('ivReps'), '::placeholder');
      const v = getComputedStyle(document.getElementById('ivReps'));
      return { ph: s.fontWeight, val: v.fontWeight, op: s.opacity };
    }""")
    check("placeholder is lighter than a real value", weights["ph"] != weights["val"], True)

    check("no page errors", errs, [])
    pg.close()

    # ── 5. Store-free — the design rule, made executable ────────────────────────────────────
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

    # ── 6. Decimal point, never a comma ─────────────────────────────────────────────────────
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

    # ── 7. Mobile, 402 px ───────────────────────────────────────────────────────────────────
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

    # ---- invalid time entry
    # Reported from real use: "10:9999" answered 0.3 km/t and "10:84" silently became 11:24. Seconds
    # have to be seconds; anything else is 0, which every caller already treats as "no value".
    print("== invalid mm:ss is rejected, not reinterpreted ==")
    pg = b.new_page()
    boot(pg)
    for src, want in [("6:15", 375), ("6", 360), ("0:45", 45),
                      ("10:84", 0), ("10:9999", 0), ("10:60", 0), ("abc", 0), ("6:-5", 0)]:
        check(f"mmSsToSecs({src!r})", pg.evaluate(f"() => mmSsToSecs({src!r})"), want)
    for src, want in [("29:30", 1770), ("1:45:00", 6300), ("29:99", 0), ("1:75:00", 0)]:
        check(f"strictHmsToSecs({src!r})", pg.evaluate(f"() => strictHmsToSecs({src!r})"), want)
    # The SHARED parser must stay lenient: it also reads the form's zone/Varighet fields and a Strava
    # import path, so tightening it would change what gets SAVED. Pinned so that stays a deliberate act.
    check("hmsToSecs itself is untouched", pg.evaluate("() => hmsToSecs('29:99')"), 1839)
    fill(pg, "#pcPace", "10:84")
    check("invalid pace clears the speed field", pg.evaluate("() => document.getElementById('pcKmh').value"), "")
    fill(pg, "#pcPace", "6:15")
    check("...and a valid one still converts", pg.evaluate("() => document.getElementById('pcKmh').value"), "9.6")
    # Visual feedback: clearing the paired field is easy to miss, and looks the same as "not filled in".
    bad = "() => document.getElementById('pcPace').classList.contains('bad-input')"
    fill(pg, "#pcPace", "10:84")
    check("invalid pace is marked", pg.evaluate(bad), True)
    fill(pg, "#pcPace", "6:15")
    check("...and unmarked once valid", pg.evaluate(bad), False)
    fill(pg, "#pcPace", "")
    check("empty is not an error", pg.evaluate(bad), False)
    # Fixing it from the SPEED side must clear a stale mark, or a corrected field keeps a red border.
    fill(pg, "#pcPace", "abc")
    fill(pg, "#pcKmh", "10.0")
    check("speed-side fix clears the mark", pg.evaluate(bad), False)
    # The error must be visible WHILE typing, so it has to beat .pc-field input:focus. --danger #e05555.
    fill(pg, "#pcPace", "10:84")
    pg.focus("#pcPace")
    check("red border wins over the focus border",
          pg.evaluate("() => getComputedStyle(document.getElementById('pcPace')).borderTopColor"),
          "rgb(224, 85, 85)")
    # Reported from real use: the speed field took a letter without complaint while pace went red, and
    # "10abc" converted as 10. Pace and speed must not disagree about what "wrong" looks like.
    badk = "() => document.getElementById('pcKmh').classList.contains('bad-input')"
    fill(pg, "#pcPace", "")
    fill(pg, "#pcKmh", "abc")
    check("invalid speed is marked too", pg.evaluate(badk), True)
    check("...and clears the pace field", pg.evaluate("() => document.getElementById('pcPace').value"), "")
    fill(pg, "#pcKmh", "10abc")
    check("trailing junk is not silently kept", pg.evaluate("() => parseDec('10abc')"), 0)
    check("...and is marked", pg.evaluate(badk), True)
    fill(pg, "#pcKmh", "10,5")
    check("a comma is still accepted", pg.evaluate(badk), False)
    check("...and converts", pg.evaluate("() => parseDec('10,5')"), 10.5)
    # A decimal must be TYPEABLE: "10." is a transient state, not an error to flash red at.
    fill(pg, "#pcKmh", "10.")
    check("a half-typed decimal is not an error", pg.evaluate(badk), False)
    # The number branch checks FORMAT, not value — 0 pause between reps is a real answer.
    fill(pg, "#ivRest", "0")
    check("a legitimate 0 is not flagged", pg.evaluate(
        "() => document.getElementById('ivRest').classList.contains('bad-input')"), False)
    check("pace fields cannot hold more than mm:ss", pg.evaluate("""
    () => [...document.querySelectorAll('#panel-tools input')]
            .filter(i => (i.placeholder || '').includes(':'))
            .every(i => i.maxLength > 0 && i.maxLength <= 7)
    """), True)
    pg.close()

    # ---- mobile keyboards
    # Reported from real use: every mm:ss field was unusable on iOS. inputmode="numeric" renders a
    # digits-only pad with no colon, so a pace could not be typed at all. Derived from the placeholder
    # rather than a list of ids, so a time field added later is covered without editing this check.
    print("== mobile keyboard per field type ==")
    pg = b.new_page()
    boot(pg)
    check("no mm:ss field uses the digits-only pad", pg.evaluate("""
    () => [...document.querySelectorAll('#panel-tools input')]
            .filter(i => (i.placeholder || '').includes(':') && i.inputMode === 'numeric')
            .map(i => i.id)
    """), [])
    # The km/t pad is fine and must stay: iOS puts a separator key on the decimal pad.
    check("speed fields keep the decimal pad", pg.evaluate("""
    () => [...document.querySelectorAll('#panel-tools input')]
            .filter(i => /^\\d+\\.\\d+$/.test(i.placeholder || ''))
            .every(i => i.inputMode === 'decimal')
    """), True)
    pg.close()

    # ---- deep link + history
    # Reported from real use: reloading on #tools landed on the form. VALID_TABS was a hand-written
    # array that never gained 'tools', so the hash failed validation and fell back. Nothing threw.
    # Note `boot()` calls switchTab('tools') directly, so every check above passed while the ROUTE
    # into the tab was broken — arriving at a panel and rendering it are separate things to test.
    print("== deep link to #tools ==")
    pg = b.new_page()
    derr = []
    pg.on("pageerror", lambda e: derr.append(str(e)))
    pg.goto(APP + "#tools")
    pg.wait_for_timeout(400)
    check("hash survives the load", pg.evaluate("() => location.hash"), "#tools")
    check("tools panel is the active one",
          pg.evaluate("() => document.querySelector('.panel.active')?.id"), "panel-tools")
    # Derived from the DOM, so it can never again list fewer tabs than exist.
    check("every tab is a valid deep-link target", pg.evaluate("""
    () => [...document.querySelectorAll('.tab')].map(t => t.dataset.tab)
            .filter(name => { location.hash = '#' + name;
                              return document.querySelector('.panel.active')?.id !== 'panel-' + name; })
    """), [])
    check("no deep-link page errors", derr, [])
    pg.close()

    b.close()

print(f"\n{passed}/{passed+failed} passed" + ("" if not failed else f"  ({failed} FAILED)"))
sys.exit(1 if failed else 0)
