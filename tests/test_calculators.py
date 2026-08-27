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

    # ⚠️ TYPED AS A BARE NUMBER — his exact report: "when I first typed 45 I expected minutes but only
    # seconds". Asserted through the FIELD, not just the parser, because the parser is shared and a
    # unit test on it would not prove this card reads it.
    pg.click("#tcModes .tc-mode[data-mode='dist']")
    fill(pg, "#tcTime", "45")
    fill(pg, "#tcPace", "7:20")
    check("45 means 45 minutes, not 45 seconds", txt(pg, "#tcOut").startswith("6.14 km"), True)
    check("...and 45:00 is the same answer, so typing it out changes nothing",
          (fill(pg, "#tcTime", "45:00"), txt(pg, "#tcOut").startswith("6.14 km"))[1], True)
    check("...while 0:45 is still forty-five seconds",
          (fill(pg, "#tcTime", "0:45"), txt(pg, "#tcOut").startswith("0.1 km"))[1], True)

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

    # ── 5. Fra plan — a session whose pace changes between reps ─────────────────────────────
    # Added 2026-08-27. Enkel assumes N x one distance x one pace, so a pyramid or a progression falls
    # outside it entirely. The text already exists (Runna writes it, the .ics carries it), so this
    # PARSES rather than asking you to rebuild the session in a form.
    #
    # THE THREE ANCHORS ARE CROSS-CHECKED AGAINST RUNNA ITSELF, which is what makes them evidence
    # rather than a snapshot of whatever the code happened to do:
    #   pyramid   47:28 vs Runna's X-WORKOUT-ESTIMATED-DURATION 3000s (= 50:00, its own value rounded
    #             UP to the nearest 5 min)
    #   400m reps 39:35 vs 2400s (= 40:00), same rounding
    #   completed 54:36 vs 55:55 actually run
    print("== Fra plan ==")
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    perrs = []
    pg.on("pageerror", lambda e: perrs.append(str(e)))
    boot(pg)

    PYRAMID = ("1km warm up at a conversational pace (no faster than 6:50/km), 90s walking rest\n\n"
               "200m at 5:05/km, 60s walking rest\n400m at 5:15/km, 90s walking rest\n"
               "800m at 5:40/km, 90s walking rest\n1.2km at 5:50/km, 120s walking rest\n"
               "800m at 5:40/km, 90s walking rest\n400m at 5:15/km, 90s walking rest\n"
               "200m at 5:05/km, 60s walking rest\n\n"
               "1km cool down at a conversational pace (or slower!)")

    P = lambda t: pg.evaluate("(t) => parseWorkoutPrescription(t)", t)
    mmss = lambda s: f"{round(s)//60}:{round(s)%60:02d}"

    r = P(PYRAMID)
    check("seven reps, expanded", len([s for s in r["segs"] if s["role"] == "work"]), 7)
    check("arbeid", mmss(r["workSecs"]), "22:18")
    check("pause", mmss(r["restSecs"]), "10:00")
    check("⚠️ blokk excludes the warm-up's rest", mmss(r["blockSecs"]), "32:18")
    check("hele økten matches Runna's own estimate", mmss(r["fullSecs"]), "47:28")
    check("...and the block itself is exact", r["blockCertainty"], "exact")
    check("...while the session is a floor (warm-up gives a ceiling)", r["certainty"], "atleast")
    check("nothing left unparsed", r["unparsed"], [])
    check("cool-down borrows the warm-up's pace, as Runna does",
          [s["paceSec"] for s in r["segs"] if s["role"] == "cooldown"], [410])

    # "N reps of:" compression, and a BAND after the target must not be read as the target.
    r = P("1.5km warm up at a conversational pace (no faster than 7:15/km), 90s walking rest\n\n"
          "5 reps of:\n• 400m at 5:40/km (5:30-5:50/km), 60s walking rest\n\n"
          "1.5km cool down at a conversational pace (or slower!)")
    check("'5 reps of:' expands to five", len([s for s in r["segs"] if s["role"] == "work"]), 5)
    check("the band is ignored; the target is used", r["segs"][1]["paceSec"], 340)
    check("400m repeats match Runna's estimate", mmss(r["fullSecs"]), "39:35")

    # A group can hold MORE than one rep — five supersets of two, not five singles.
    r = P("3 reps of:\n• 1km at 5:40/km, 90s walking rest\n• 400m at 5:10/km, 60s walking rest")
    check("a superset repeats the whole body", [s["km"] for s in r["segs"]],
          [1, 0.4, 1, 0.4, 1, 0.4])

    # The other grouping form, fenced by dashes.
    r = P("Repeat the following 3x:\n----------\n1000m at 5:30/km\n500m at 6:10/km\n----------\n\n90s walking rest")
    check("'Repeat the following 3x:' expands too", len(r["segs"]), 6)
    check("...and the trailing rest attaches to the last rep", r["segs"][-1]["restSec"], 90)

    # ⚠️ PAST RUNS MUST NOT PRODUCE A WRONG ANSWER. A completed event is in kph, and carries a
    # "♻️ Laps:" block of what was ACTUALLY run — including the walking rests as 15:00/km placeholder
    # laps. Totalling those would inflate every number on the card while looking perfectly plausible.
    COMPLETED = ("1.5km warm up at a conversational pace (no faster than 8.1kph), 90s walking rest\n\n"
                 "200m at 10.6kph, 60s walking rest\n400m at 10.3kph, 90s walking rest\n"
                 "800m at 9.6kph, 90s walking rest\n1.2km at 9.4kph, 120s walking rest\n"
                 "800m at 9.6kph, 90s walking rest\n400m at 10.3kph, 90s walking rest\n"
                 "200m at 10.6kph, 60s walking rest\n\n"
                 "1km cool down at a conversational pace (or slower!)\n\n"
                 "♻️ Laps:\n1.50 km @ 8:14 /km\n0.10 km @ 15:00 /km\n0.20 km @ 5:39 /km\n"
                 "0.00 km @ 59:59 /km")
    r = P(COMPLETED)
    check("kph parses as well as pace", len([s for s in r["segs"] if s["role"] == "work"]), 7)
    check("...to the same seven reps, not seven plus eighteen laps", len(r["segs"]), 9)
    check("hele økten vs the 55:55 actually run", mmss(r["fullSecs"]), "54:36")
    check("⚠️ no 15:00/km rest lap leaked in",
          any(abs(s["paceSec"] - 900) < 1 for s in r["segs"] if s["paceSec"]), False)

    # Prose interpolated mid-line names a SECOND pace. The first is the one to run.
    r = P("4 reps of:\n• 400m at 5:05/km, just faster than your target pace of 5:20/km, 90s walking rest")
    check("a second pace in the prose is ignored", r["segs"][0]["paceSec"], 305)

    # Runna's own header line carries "6km" and "45m" and is not a segment.
    r = P("Intervals • 6km • 45m - 50m\n\n200m at 5:05/km, 60s walking rest")
    check("the header line is not parsed as distance", [s["km"] for s in r["segs"]], [0.2])
    # ⚠️ …and it must not land in `unparsed` either. Falsified: dropping the header filter left the
    # segment list correct — RX_DIST is anchored, so "Intervals • 6km" never matched — and the check
    # above passed. What it actually broke was the card warning "these lines were not understood"
    # about Runna's own title, on every paste. That warning is the mechanism that makes the parser
    # safe to trust; crying wolf on every session is exactly how it stops being read.
    check("...nor reported as an unrecognised line", r["unparsed"], [])

    # A range as the PRIMARY target (not a band after one) has no single pace — midpoint, flagged.
    r = P("5km race at 5:30-5:40/km")
    check("a primary range uses the midpoint", r["segs"][0]["paceSec"], 335)
    check("...and says the number is not exact", r["certainty"], "range")

    # ⚠️ THE HONESTY CASE. Most Long runs are "8km at a conversational pace" with no pace ANYWHERE —
    # unlike a cool-down there is no ceiling in the text to borrow. The time must not silently cover
    # only part of the distance.
    r = P("8km at a conversational pace\n3km at 5:50/km")
    check("an untimeable segment is kept, not dropped", len(r["segs"]), 2)
    check("...and reported as unknown distance", r["unknownKm"], 8)
    check("...with the timed distance stated separately", (r["timedKm"], r["workKm"]), (3, 11))
    check("...and the whole thing graded partial", r["certainty"], "partial")

    check("strength is refused outright, not totalled as zero",
          P("4 sets of:\n• Bodyweight Squat\n• Fire Hydrants"), None)
    check("gibberish is refused", P("hva som helst"), None)
    check("empty is refused", P(""), None)

    # A line with a distance but nothing else is REPORTED, never dropped — a dropped rep understates
    # the block, which is the direction that gets you off the treadmill too early.
    r = P("200m at 5:05/km, 60s walking rest\nsomething Runna invented next year")
    check("an unrecognised line is listed", r["unparsed"], ["something Runna invented next year"])

    print("== Fra plan, on screen ==")
    check("Enkel is the default", pg.locator("#ivEnkel").is_visible(), True)
    check("...and Fra plan is hidden", pg.locator("#ivPlan").is_visible(), False)
    pg.click("#ivModes .tc-mode[data-mode='plan']")
    pg.wait_for_timeout(200)
    check("toggling swaps them", (pg.locator("#ivEnkel").is_visible(), pg.locator("#ivPlan").is_visible()),
          (False, True))
    check("empty box asks, rather than showing 0", txt(pg, "#ivPlanOut").startswith("–"), True)

    fill(pg, "#ivPaste", PYRAMID)
    pg.wait_for_timeout(250)
    check("the block leads", txt(pg, "#ivPlanOut").startswith("32:18 BLOKK"), True)
    check("...and the session is marked approximate", "~47:28" in txt(pg, "#ivPlanOut"), True)
    check("the treadmill setting is the headline",
          txt(pg, "#ivPlanHero"), "Raskeste drag: 11.8 km/t · 5:05 /km")
    segs = txt(pg, "#ivPlanSegs")
    check("every rep is listed with its speed", "1.2 km 10.3 km/t 7:00" in segs, True)
    check("...and the warm-up is shown as context", segs.startswith("oppv. 1 km 8.8 km/t 6:50"), True)
    check("the floor is explained, not just marked",
          "minimum" in txt(pg, "#ivPlanNote"), True)

    # The partial case on screen: the lead stat must be true BY ITSELF. "17:30" beside "11 km" reads
    # as a 1:35/km session to anyone who only takes in the big number.
    fill(pg, "#ivPaste", "8km at a conversational pace\n3km at 5:50/km")
    pg.wait_for_timeout(250)
    check("⚠️ the lead stat names what its time actually covers",
          "3 AV 11 KM" in txt(pg, "#ivPlanOut").upper(), True)
    check("...and the note says which segment had no pace",
          "conversational" in txt(pg, "#ivPlanNote"), True)

    check("no page errors", perrs, [])
    pg.close()

    # ── 6. Store-free — the design rule, made executable ────────────────────────────────────
    print("== reads nothing from Store ==")

    def snapshot(seed):
        p = b.new_page(viewport={"width": 1280, "height": 900})
        boot(p, seed=seed)
        p.fill("#tcDist", "10"); p.fill("#tcPace", "6:15")
        p.fill("#ivReps", "6");  p.fill("#ivVal", "400")
        p.fill("#ivPace", "5:30"); p.fill("#ivRest", "90")
        p.wait_for_timeout(200)
        # ⚠️ Read the Enkel surfaces BEFORE switching mode. Fra plan hides #ivEnkel, and inner_text on
        # a hidden element returns "" — so capturing afterwards would compare "" to "" and report
        # agreement for half the snapshot. This suite's whole point is that it cannot do that.
        s = (txt(p, "#tcOut"), txt(p, "#tcSplits"), txt(p, "#ivHero"), txt(p, "#ivOut"),
             txt(p, "#pcTable"))
        assert all(s), "a Store-free snapshot went blank — the selectors moved"
        # Fra plan too. It is the ONE tool whose input the app also stores, so it is the one most
        # likely to acquire a Store read by accident — pasting must stay the only way in.
        p.click("#ivModes .tc-mode[data-mode='plan']")
        p.fill("#ivPaste", "200m at 5:05/km, 60s walking rest\n400m at 5:15/km, 90s walking rest")
        p.wait_for_timeout(250)
        s += (txt(p, "#ivPlanOut"), txt(p, "#ivPlanSegs"), txt(p, "#ivPlanHero"))
        p.close()
        return s

    empty, seeded = snapshot(False), snapshot(True)
    check("output identical with and without sessions", empty, seeded)
    check("...and it was not simply blank", empty[0].startswith("1:02:30"), True)

    # ── 7. Decimal point, never a comma ─────────────────────────────────────────────────────
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

    # ── 8. Mobile, 402 px ───────────────────────────────────────────────────────────────────
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
    # ⚠️ A BARE NUMBER IS MINUTES, and must agree with mmSsToSecs('6') == 360 pinned just above.
    # Reported from real use 2026-08-26: typing 45 in Tid meant 45 SECONDS while 6 in the Tempo field
    # directly above it meant 6:00. 45 and 45:00 now agree, which also means the live recalculation
    # no longer passes through a wrong answer while you finish typing.
    for src, want in [("29:30", 1770), ("1:45:00", 6300), ("29:99", 0), ("1:75:00", 0),
                      ("45", 2700), ("45:00", 2700), ("0:45", 45), ("1", 60), ("0", 0)]:
        check(f"strictHmsToSecs({src!r})", pg.evaluate(f"() => strictHmsToSecs({src!r})"), want)
    check("bare number agrees across the card's two time parsers",
          pg.evaluate("() => strictHmsToSecs('45') === mmSsToSecs('45')"), True)
    # The SHARED parser must stay lenient: it also reads the form's zone/Varighet fields and a Strava
    # import path, so tightening it would change what gets SAVED. Pinned so that stays a deliberate act.
    check("hmsToSecs itself is untouched", pg.evaluate("() => hmsToSecs('29:99')"), 1839)
    # ⚠️ AND the bare-number rule must NOT have leaked into it. Falsified: moving the minutes reading
    # down into hmsToSecs passed 135/135 here and 59/59 in test_goals, because the only pin above
    # covers the two-part case. A bare number is the whole Varighet field — reading it as minutes
    # would silently multiply a saved session duration by 60.
    check("...and a bare number is still SECONDS there — the save path is not redefined",
          pg.evaluate("() => hmsToSecs('45')"), 45)
    check("...so the two parsers deliberately DISAGREE on a bare number",
          pg.evaluate("() => hmsToSecs('45') !== strictHmsToSecs('45')"), True)
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
