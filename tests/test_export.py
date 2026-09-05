"""Verify the AI/TSV export blocks — in particular the [Analyse] section.  (2026-08-18)

Standalone — NOT part of run_all.py, which is the fast no-browser gate. Run directly:
    python tests/test_export.py           (needs Playwright + WebKit)

Why this exists: formatSessionTsv had NO coverage of any kind before this file. The header/row fusion
(3bd33d4) was verified by an ad-hoc snapshot that was never committed, and that snapshot silently
tested the wrong thing for a while — its fixture used `lopetype` where the app reads `s.løpetype`, so
the Tredemølle branch never ran.

The [Analyse] block is branchy in ways a column never was: outdoor-only for run/walk, both venues for
the aerobic metrics, and gated on the SAME staleness rules the detail panel uses. Each of those is a
way to emit something the app itself would refuse to show.

No local data file exists — sessions are synthesised in-page.
"""
import pathlib, sys
sys.stdout.reconfigure(encoding='utf-8')
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


# Versions and thresholds are READ FROM THE PAGE, never hardcoded here: a copy would go stale the
# first time an analysis version is bumped, and the suite would then test staleness handling by
# accident instead of the thing it names.
BUILD = """
(cfg) => {
  const thr = Continuity.thresholds();
  const cont = (over) => Object.assign({
    version: CONTINUITY_ANALYSIS_VERSION, thresholdVersion: CONTINUITY_THRESHOLD_VERSION,
    walkMaxKmh: thr.definiteWalkMaxKmh, runMinKmh: thr.definiteRunMinKmh,
    runningRatio: 0.95, walkingRatio: 0.02, unclassifiedRatio: 0.03,
    longestContinuousRunMeters: 4400, longestContinuousRunSeconds: 1757,
    runToWalkTransitions: 2, datakvalitet: 'høy', warnings: [],
    uphillWalkingDistanceMeters: 43, uphillWalkingTimeSeconds: 24,
  }, over || {});
  const aero = (over) => Object.assign({
    version: AEROBIC_ANALYSIS_VERSION, hasDecoupling: true, decouplingPercent: 9.14,
    hasCadence: true, avgCadenceSpm: 159,
  }, over || {});
  const base = (over) => Object.assign({
    id: 'x', dato: '2026-08-10', uke: '2026-33', oktnavn: 'Runna Easy', okttype: 'Easy',
    treningsplan: 'Runna', løpetype: 'utendors', varighet: 1800, distanse: 5,
    tempo: 360, snittkmh: 10, soner: [0, 600, 900, 300, 0],
  }, over || {});
  return {
    outdoor:  formatSessionTsv([base({ stravaAnalysis: { continuity: cont(), aerobic: aero() } })]),
    treadmill:formatSessionTsv([base({ løpetype: 'treadmill',
                                       stravaAnalysis: { continuity: cont(), aerobic: aero() } })]),
    stale:    formatSessionTsv([base({ stravaAnalysis: {
                                       continuity: cont({ walkMaxKmh: thr.definiteWalkMaxKmh + 1 }),
                                       aerobic: aero() } })]),
    staleAero:formatSessionTsv([base({ stravaAnalysis: {
                                       continuity: cont(), aerobic: aero({ version: 'nope' }) } })]),
    lowQual:  formatSessionTsv([base({ stravaAnalysis: { continuity: cont({
                                       datakvalitet: 'lav', warnings: ['Mangler kadens-strøm'] }) } })]),
    highWarn: formatSessionTsv([base({ stravaAnalysis: { continuity: cont({
                                       warnings: ['Mangler kadens-strøm'] }) } })]),
    noUphill: formatSessionTsv([base({ stravaAnalysis: { continuity: cont({
                                       uphillWalkingTimeSeconds: null }) } })]),
    cadOnly:  formatSessionTsv([base({ løpetype: 'treadmill', stravaAnalysis: {
                                       aerobic: aero({ hasDecoupling: false }) } })]),
    none:     formatSessionTsv([base()]),
    withNote: formatSessionTsv([base({ notater: 'Kjentes tungt.',
                                       stravaAnalysis: { aerobic: aero() } })]),
    // «Uten notater» (2026-09-05). Same session three ways, so the checkbox can be compared against
    // the note being present and against the note never having existed.
    noNotes:  formatSessionTsv([base({ notater: 'Kjentes tungt.',
                                       stravaAnalysis: { aerobic: aero() } })], { omitNotes: true }),
    neverHad: formatSessionTsv([base({ stravaAnalysis: { aerobic: aero() } })], { omitNotes: true }),
    // Notes off must NOT take the plan's prescription with it — different provenance, different call.
    descOnly: formatSessionTsv([base({ notater: 'Privat notat.', beskrivelse: '3x1km @ 4:30' })],
                               { omitNotes: true }),
    descKept: formatSessionTsv([base({ notater: 'Privat notat.', beskrivelse: '3x1km @ 4:30' })]),
  };
}"""

with sync_playwright() as pw:
    b = pw.webkit.launch()
    p = b.new_page(viewport={"width": 1280, "height": 900})
    errs = []
    p.on("pageerror", lambda e: errs.append(str(e)))
    p.goto(APP)
    p.wait_for_timeout(400)
    out = p.evaluate(BUILD, {})

    # ── The outdoor block: every line, in his order ─────────────────────────────────────────
    print("== [Analyse] on an outdoor run ==")
    o = out["outdoor"]
    check("block is labelled", "[Analyse]" in o, True)
    check("run/walk ratios", "Run/walk: 95% løping · 2% gange · 3% uklart" in o, True)
    check("longest continuous run", "Lengste løp: 4.4 km · 29:17" in o, True)
    check("transitions", "Overganger til gange: 2" in o, True)
    check("uphill walking", "Gange i motbakke: 43 m · 00:24" in o, True)
    check("data quality", "Datakvalitet: høy" in o, True)
    check("HR drift, signed", "HR-drift: +9.1%" in o, True)
    check("cadence", "Kadens: 159 spm" in o, True)

    # ── THE VENUE RULE ──────────────────────────────────────────────────────────────────────
    # Run/walk reads GPS speed second by second, so it is outdoor-only. The aerobic metrics read the
    # HR sensor and accelerometer and apply indoors too. A treadmill session gets the second half and
    # NO placeholder for the first — the data row already says Tredemølle.
    print("== outdoor-only run/walk vs both-venue aerobic ==")
    t = out["treadmill"]
    check("treadmill drops run/walk", "Run/walk:" in t, False)
    check("...and its sub-lines with it", "Lengste løp:" in t or "Datakvalitet:" in t, False)
    check("...but keeps HR-drift", "HR-drift: +9.1%" in t, True)
    check("...and cadence", "Kadens: 159 spm" in t, True)
    check("...with no placeholder for the missing half", "n/a" in t.lower(), False)
    check("...and the row still names the venue", "Tredemølle" in t, True)

    # ── STALENESS: never emit what the app refuses to show ──────────────────────────────────
    # A run/walk result computed under different speed thresholds is hidden in the detail panel until
    # re-analysed. Exporting it anyway would put numbers in a file that the app itself disowns.
    print("== stale results are withheld, exactly as the panel withholds them ==")
    st = out["stale"]
    check("threshold change withholds run/walk", "Run/walk:" in st, False)
    check("...while the aerobic half is untouched", "HR-drift: +9.1%" in st, True)
    sa = out["staleAero"]
    check("aerobic version bump withholds HR-drift", "HR-drift:" in sa, False)
    check("...while run/walk is untouched", "Run/walk: 95% løping" in sa, True)

    # ── Warnings only when the quality is not high ──────────────────────────────────────────
    print("== warnings explain a low quality, and only then ==")
    check("low quality names the reason", "Forbehold: Mangler kadens-strøm" in out["lowQual"], True)
    check("...and says the quality is low", "Datakvalitet: lav" in out["lowQual"], True)
    check("high quality stays quiet even with warnings stored",
          "Forbehold:" in out["highWarn"], False)

    # ── Absent parts are absent, not blank ──────────────────────────────────────────────────
    print("== nothing to say means nothing printed ==")
    check("no uphill data, no uphill line", "Gange i motbakke:" in out["noUphill"], False)
    check("...but the rest of run/walk stays", "Run/walk: 95% løping" in out["noUphill"], True)
    check("cadence without drift prints only cadence",
          "HR-drift:" in out["cadOnly"], False)
    check("...and does print the cadence", "Kadens: 159 spm" in out["cadOnly"], True)
    check("a session with no analysis gets no block", "[Analyse]" in out["none"], False)

    # ── Placement: written above the row, measured below it ─────────────────────────────────
    # Everything a human wrote goes above the data row; everything derived from Strava goes below it,
    # so the row and its analysis read as one machine-measured group. Notes keep their place
    # immediately above the row — that adjacency is why this block format exists at all.
    print("== notes above the data row, analysis below it ==")
    w = out["withNote"]
    # The data row STARTS with the formatted date, not the session name — an earlier version of this
    # check anchored on "Runna Easy" and matched mid-row, so it measured a gap that was really the
    # row's own first two fields.
    ROW = "8/10/2026\t2026-33"
    check("notes come before the data row", w.index("Kjentes tungt.") < w.index(ROW), True)
    check("analysis comes after it", w.index(ROW) < w.index("[Analyse]"), True)
    check("...and nothing at all separates note from row",
          w.split("Kjentes tungt.")[1].startswith("\n\n" + ROW), True)

    # ── «Uten notater» (2026-09-05) ────────────────────────────────────────────────────────
    # ⚠️ The positive control comes FIRST. "the note is absent" is trivially true of a broken export,
    # an empty string, or a fixture that never carried a note — so it proves nothing on its own.
    # The note is LABELLED (2026-09-05). It used to be the only unlabelled section, so with a
    # multi-paragraph Øktbeskrivelse above it — parts are separated by blank lines — the note read as
    # one more paragraph of the plan's prescription, and anything parsing the export would credit
    # Runna with what he wrote.
    print("== [Notater] header ==")
    check("the note carries a header", "[Notater]" in out["withNote"], True)
    check("...immediately above the note text",
          out["withNote"].split("[Notater]")[1].startswith("\nKjentes tungt."), True)
    check("...and after the description, not inside it",
          out["descKept"].index("[Øktbeskrivelse]") < out["descKept"].index("[Notater]"), True)

    print("== uten notater ==")
    check("control: the note IS there without the option", "Kjentes tungt." in out["withNote"], True)
    check("omitNotes drops it", "Kjentes tungt." in out["noNotes"], False)
    # A label left behind announcing a section that isn't there is worse than no label at all.
    check("...taking its header with it", "[Notater]" in out["noNotes"], False)
    # ⚠️ And the block must still be WELL-FORMED, not merely note-free. Removing the only metaPart
    # changes which branch builds the body (`metaParts.length ? … : …`), so this is the one line that
    # would catch a stray blank line or a lost header — invisible to a substring check for absence.
    check("...and the block is byte-identical to one that never had a note",
          out["noNotes"] == out["neverHad"], True)

    # Notater and Øktbeskrivelse are different things: one you wrote, one the programme prescribed.
    print("== Øktbeskrivelse survives ==")
    check("control: both present by default",
          ("Privat notat." in out["descKept"]) and ("3x1km @ 4:30" in out["descKept"]), True)
    check("omitNotes drops only the note", "Privat notat." in out["descOnly"], False)
    check("...and keeps the prescription", "3x1km @ 4:30" in out["descOnly"], True)
    check("...with its [Øktbeskrivelse] label intact", "[Øktbeskrivelse]" in out["descOnly"], True)

    # ── The checkbox is actually WIRED — to all three buttons ──────────────────────────────
    # ⚠️ Everything above tests the `omitNotes` OPTION. That would all pass with a checkbox that does
    # nothing, which is the likelier bug: three separate handlers each have to read it, and one left
    # behind is an export that honours the box from one button and ignores it from another.
    # Captures the second ARGUMENT rather than the output, so no session data is needed and the
    # assertion is exactly "did this button pass the checkbox state".
    print("== checkbox wiring ==")
    # A real logged session, because btnCopySelected is disabled until a row is selected — forcing it
    # enabled would bypass the path being tested.
    p.evaluate("""() => localStorage.setItem('lpl_cache', JSON.stringify({
      sessions:[{ id:'x1', dato:'2026-08-10', uke:'2026-33', oktnavn:'Runna Easy', okttype:'Easy',
                  treningsplan:'Runna', løpetype:'utendors', varighet:1800, distanse:5, tempo:360,
                  soner:[0,600,900,300,0], notater:'Kjentes tungt.' }],
      shoes:[], shoeDefaults:{}, goals:{}, events:[], plannedSessions:[],
      settings:{zones:[]}, lastUpdated:'' }))""")
    p.reload()
    p.wait_for_timeout(600)
    p.evaluate("""() => {
      switchTab('log');
      window.__calls = [];
      const real = window.formatSessionTsv;
      window.formatSessionTsv = (s, o) => { window.__calls.push(o); return real(s, o); };
      window.copyToClipboard = async () => {};   // headless has no clipboard permission
    }""")
    BUTTONS = ["btnCopyAll", "btnDownloadTsv", "btnCopySelected"]

    def opts_after(btn, ticked):
        p.evaluate(f"() => {{ document.getElementById('chkNoNotes').checked = {str(ticked).lower()}; window.__calls = []; }}")
        # btnCopySelected is disabled until something is selected; select all first.
        if btn == "btnCopySelected":
            p.evaluate("() => { document.getElementById('chkSelectAll').checked = true; "
                       "document.getElementById('chkSelectAll').dispatchEvent(new Event('change')); }")
        p.evaluate(f"() => document.getElementById('{btn}').click()")
        p.wait_for_timeout(150)
        return p.evaluate("() => window.__calls.map(o => o && o.omitNotes)")

    for btn in BUTTONS:
        check(f"{btn} passes omitNotes:true when ticked", opts_after(btn, True), [True])
        check(f"{btn} passes omitNotes:false when clear", opts_after(btn, False), [False])

    check("no page errors", errs, [])
    b.close()

print(f"\n{passed}/{passed+failed} passed" + ("" if not failed else f"  ({failed} FAILED)"))
sys.exit(1 if failed else 0)
