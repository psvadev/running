"""Verify Kommende blokker — the list of training blocks that are still only ideas.  (2026-08-19)

Standalone — NOT part of run_all.py, which is the fast no-browser gate. Run directly:
    python tests/test_blocks.py           (needs Playwright + WebKit)

Its own suite rather than an appendix to test_race_events.py, whose docstring promises races and
.ics imports. Same "a surface must show what its heading promises" rule, applied to a test file.

What actually needs guarding here:

  1. IT MUST FEED NOTHING. A future Plan event was the obvious home and was rejected for a concrete
     reason: computeBlocks sets `endDate = evt.endDate || planEvents[i+1]?.date || today`, so a
     future plan event stretches the LIVE block to that date and flips `endIsOpen` — which also moves
     what the .ics import scopes into it. This list exists precisely so an idea cannot do that, and
     "cannot" is a claim worth executing rather than commenting.
  2. THE SHARED PICKER NOW HAS TWO DIRECTIONS. monthYearPickerHTML gained a `forward` flag: Sko keeps
     its backwards years, blocks look ahead. A backward-compatible optional parameter is an argument,
     not evidence — so both directions are asserted against each other.
  3. UNDATED ENTRIES SORT LAST. "ikke bestemt" is a real answer here, not a gap to float to the top.

No local data file exists; every session is synthesised in-page.
"""
import pathlib, sys
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

APP = (pathlib.Path(__file__).resolve().parent.parent / "puls.html").as_uri()
passed = failed = 0

# Tuesday 2026-08-18, midday — pinned so "years forward" and the derived Start blokk dates are
# absolute. See memory reference-test-gate, third failure mode.
FREEZE = """
(() => {
  const R = Date;
  const fixed = new R(2026, 7, 18, 12, 0, 0).getTime();
  function F(...a) { return a.length ? new R(...a) : new R(fixed); }
  F.prototype = R.prototype; F.now = () => fixed; F.parse = R.parse; F.UTC = R.UTC;
  window.Date = F;
})();
"""


def check(name, got, want):
    global passed, failed
    if got == want:
        passed += 1
        print(f"  PASS {name}")
    else:
        failed += 1
        print(f"  FAIL {name}\n       got  {got!r}\n       want {want!r}")


# One real, dated plan event plus runs inside it — so computeBlocks has an actual block to return and
# "unchanged" is a claim about something rather than about an empty array.
SEED = """() => {
  const run = (dato, distanse) => ({
    id: dato, dato, uke: '2026-30', oktnavn: 'Tur', okttype: 'Easy', treningsplan: 'Runna',
    løpetype: 'utendors', distanse, varighet: distanse * 360, tempo: 360, soner: [0,0,0,0,0],
  });
  localStorage.setItem('lpl_cache', JSON.stringify({
    sessions: [run('2026-07-20', 6), run('2026-07-27', 8), run('2026-08-03', 7)],
    shoes: [], goals: {}, plannedSessions: [], settings: { zones: [] },
    events: [{ id:'p1', type:'plan', title:'Runna 5K', date:'2026-07-06', endDate:'2026-09-13' }],
    lastUpdated: '' }));
}"""

ROWS = """() => [...document.querySelectorAll('#upcomingBlockList > div')].map(r => {
  const c = [...r.children].map(x => x.textContent.trim().replace(/\\s+/g, ' '));
  return { kind: c[0], when: c[1], weeks: c[2], note: c[3] };
})"""


def boot(pg):
    pg.add_init_script(FREEZE)
    pg.goto(APP)
    pg.evaluate(SEED)
    pg.goto(APP)
    pg.evaluate("() => switchTab('plan')")
    pg.wait_for_timeout(400)


with sync_playwright() as pw:
    b = pw.webkit.launch()
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("dialog", lambda d: d.accept())
    boot(pg)

    # ── 1. The empty state and the picker ───────────────────────────────────────────────────
    print("== the card before anything is noted ==")
    check("empty state says so",
          pg.locator('#upcomingBlockList').inner_text().startswith('Ingen'), True)
    kinds = pg.eval_on_selector_all('#newUbKind option', "o => o.map(x => x.value)")
    check("the kind picker is the block list, not the PR distances",
          kinds, pg.evaluate("() => UPCOMING_BLOCK_KINDS.map(k => k.key)"))
    check("...so 400 m and 15 km are not offered",
          any(k in kinds for k in ('400m', '1k', '15k')), False)

    # ── 2. THE SHARED PICKER, BOTH DIRECTIONS ───────────────────────────────────────────────
    # monthYearPickerHTML gained an optional `forward`. Assert the two modes against each other
    # rather than against years written down here, which would go stale on 1 January.
    print("== one picker helper, two year directions ==")
    yrs = pg.evaluate("""() => {
      const grab = html => { const d = document.createElement('div'); d.innerHTML = html;
        return [...d.querySelectorAll('select')][1].options.length > 1
          ? [...d.querySelectorAll('select')][1].options : []; };
      const back = [...grab(monthYearPickerHTML('t1', '', true))].map(o => o.value).filter(Boolean);
      const fwd  = [...grab(monthYearPickerHTML('t2', '', true, true))].map(o => o.value).filter(Boolean);
      return { back, fwd, now: String(new Date().getFullYear()) };
    }""")
    check("Sko's picker still runs backwards from this year",
          (yrs['back'][0], yrs['back'][1] < yrs['back'][0]), (yrs['now'], True))
    check("...and still reaches 20 years back", len(yrs['back']), 21)
    check("the block picker runs forwards from this year",
          (yrs['fwd'][0], yrs['fwd'][-1]), (yrs['now'], str(int(yrs['now']) + 3)))
    check("...and offers no past year", any(y < yrs['now'] for y in yrs['fwd']), False)
    # ⚠️ The three above test the HELPER. This one tests the CALL SITE — that the card actually
    # passes `forward`. Without it, dropping the flag only surfaced as a 30-second Playwright timeout
    # deep in section 3 ("did not find some options"), which is a crash, not a diagnosis.
    live = pg.eval_on_selector_all('#newUb-y option', "o => o.map(x => x.value).filter(Boolean)")
    check("the card's own picker looks forward too",
          (live[0], live[-1]), (yrs['now'], str(int(yrs['now']) + 3)))

    # ── 3. Adding, ordering, and "ikke bestemt" ─────────────────────────────────────────────
    print("== the list orders itself by rough month ==")

    def add(kind, month=None, year=None, weeks=None, note=None):
        pg.select_option('#newUbKind', kind)
        if month: pg.select_option('#newUb-m', month)
        if year:  pg.select_option('#newUb-y', year)
        if weeks: pg.fill('#newUbWeeks', str(weeks))
        if note:  pg.fill('#newUbNote', note)
        pg.click('#btnAddUb')
        pg.wait_for_timeout(120)

    store = lambda: pg.evaluate("() => Store.data.upcomingBlocks || []")
    ub = lambda kind: [x for x in store() if x['kind'] == kind][0]

    # Entered latest-first, and the undated one in the middle, so neither entry order nor a
    # front-loaded blank could produce the expected result by accident.
    add('half', '01', '2027', 16, 'etter 10K')
    add('marathon')
    add('10k', '10', '2026', 12)
    rows = pg.evaluate(ROWS)
    check("sorted by month, undated last",
          [r['kind'] for r in rows], ['10 km', 'Halvmaraton', 'Maraton'])
    check("the month reads as a rough month", rows[0]['when'], 'okt 2026')
    check("...and 2027 is reachable at all", rows[1]['when'], 'jan 2027')
    check("no month reads 'ikke bestemt'", rows[2]['when'], 'ikke bestemt')
    check("weeks are approximate", rows[0]['weeks'], '~12 uker')
    check("...and absent when unset", rows[2]['weeks'], '')
    check("the note is carried", rows[1]['note'], 'etter 10K')
    check("everything but the kind is optional",
          store()[1], {'id': store()[1]['id'], 'kind': 'marathon',
                       'startMonth': None, 'weeks': None, 'note': None})

    # ── 4. ⚠️ IT FEEDS NOTHING — the reason this list exists at all ──────────────────────────
    print("== an idea does not become a training block ==")
    after = pg.evaluate("() => JSON.stringify(computeBlocks(Store.data.sessions))")
    before = pg.evaluate("""() => {
      const keep = Store.data.upcomingBlocks;
      Store.data.upcomingBlocks = [];
      const out = JSON.stringify(computeBlocks(Store.data.sessions));
      Store.data.upcomingBlocks = keep;
      return out;
    }""")
    check("computeBlocks is byte-identical with and without them", after, before)
    check("...and it did return a real block", '"startDate":"2026-07-06"' in after, True)
    check("the live block still ends where its event says", '"endDate":"2026-09-13"' in after, True)
    check("no Kommende card appeared on the dashboard",
          pg.evaluate("() => { switchTab('dash'); return (document.getElementById('blocksCard')||{}).innerText || ''; }")
            .count('Kommende'), 0)
    pg.evaluate("() => switchTab('plan')")
    pg.wait_for_timeout(300)
    check("events are untouched", pg.evaluate("() => Store.data.events.length"), 1)

    # ── 5. Start blokk — prefill, and strictly nothing else ─────────────────────────────────
    print("== Start blokk fills the Hendelser form and stops ==")
    evts_before = pg.evaluate("() => JSON.stringify(Store.data.events)")
    ub_before = len(store())
    pg.click(f'[data-start-ub="{ub("10k")["id"]}"]')
    pg.wait_for_timeout(200)
    check("type is Plan", pg.locator('#newEvtType').input_value(), 'plan')
    check("plan targets are visible (syncEventFields ran)",
          pg.locator('#evtPlanTargets').is_visible(), True)
    check("title is the bare distance, no vendor invented",
          pg.locator('#newEvtTitle').input_value(), '10 km')
    check("start date is the first of the rough month",
          pg.locator('#newEvtDate').input_value(), '2026-10-01')
    check("end date is exactly weeks x 7 later",
          pg.locator('#newEvtEndDate').input_value(), '2026-12-24')
    check("it created no event", pg.evaluate("() => JSON.stringify(Store.data.events)"), evts_before)
    check("...and deleted no idea", len(store()), ub_before)

    # An entry with no month falls back to today rather than an empty date, and leaves the end blank.
    pg.click(f'[data-start-ub="{ub("marathon")["id"]}"]')
    pg.wait_for_timeout(200)
    check("undated block starts from today", pg.locator('#newEvtDate').input_value(), '2026-08-18')
    check("...with no invented end date", pg.locator('#newEvtEndDate').input_value(), '')

    # ⚠️ Start blokk fills the ADD form, so it must first LEAVE any edit in progress. Without
    # cancelEventEdit() the form still carries editingEventId, and addEvent() branches on it —
    # saving would call Store.updateEvent and overwrite the real training block with the idea.
    # The targets ride along too: syncEventFields only clears them when the type is NOT plan.
    print("== Start blokk during an event edit does not hijack that event ==")
    pg.click('[data-edit-event="p1"]')
    pg.wait_for_timeout(150)
    pg.fill('#newEvtTotalKmTarget', '250')
    check("we are genuinely mid-edit", pg.locator('#btnAddEvent').inner_text(), 'Lagre endringer')
    pg.click(f'[data-start-ub="{ub("10k")["id"]}"]')
    pg.wait_for_timeout(200)
    check("the form left edit mode", pg.locator('#btnAddEvent').inner_text(), '+ Legg til')
    check("...and dropped the edited event's target",
          pg.locator('#newEvtTotalKmTarget').input_value(), '')
    check("plan targets are still visible", pg.locator('#evtPlanTargets').is_visible(), True)
    pg.click('#btnAddEvent')
    pg.wait_for_timeout(200)
    evts = pg.evaluate("() => Store.data.events")
    check("saving ADDED an event rather than overwriting one", len(evts), 2)
    orig = [e for e in evts if e['id'] == 'p1']
    check("...and the original block is untouched", orig and orig[0]['title'], 'Runna 5K')
    check("...including its dates", orig and orig[0]['endDate'], '2026-09-13')
    pg.evaluate("() => { Store.data.events = Store.data.events.filter(e => e.id === 'p1');"
                "        Settings.renderEventList(); }")
    pg.wait_for_timeout(120)

    # ── 6. Edit and delete ──────────────────────────────────────────────────────────────────
    print("== edit in place, and delete ==")
    hm = [x for x in store() if x['kind'] == 'half'][0]
    pg.click(f'[data-edit-ub="{hm["id"]}"]')
    pg.wait_for_timeout(120)
    check("month is prefilled", pg.locator('#newUb-m').input_value(), '01')
    check("...and the year, which only exists because the range looks forward",
          pg.locator('#newUb-y').input_value(), '2027')
    check("weeks prefilled", pg.locator('#newUbWeeks').input_value(), '16')
    check("the button says Oppdater", pg.locator('#btnAddUb').inner_text(), 'Oppdater')
    pg.fill('#newUbWeeks', '18')
    pg.click('#btnAddUb')
    pg.wait_for_timeout(150)
    check("editing updates in place, adding nothing", len(store()), 3)
    check("...with the new value", [x for x in store() if x['kind'] == 'half'][0]['weeks'], 18)
    check("...and restores the button", pg.locator('#btnAddUb').inner_text(), '+ Legg til')

    pg.click(f'[data-del-ub="{hm["id"]}"]')
    pg.wait_for_timeout(150)
    check("delete removes exactly one", sorted(x['kind'] for x in store()), ['10k', 'marathon'])

    # ── 7. Round-trip, with no _migrate entry ───────────────────────────────────────────────
    print("== it survives export and re-import ==")
    rt = pg.evaluate("""() => {
      const json = Store.toJSON();
      Store.load(json);
      return (Store.data.upcomingBlocks || []).map(b => b.kind).sort();
    }""")
    check("the key round-trips through toJSON/load", rt, ['10k', 'marathon'])
    check("...without a _migrate default",
          pg.evaluate("() => { const s = Store._migrate.toString(); return s.includes('upcomingBlocks'); }"), False)

    # ── 8. Mobile ───────────────────────────────────────────────────────────────────────────
    print("== 402 px ==")
    pg.set_viewport_size({"width": 402, "height": 900})
    pg.wait_for_timeout(250)
    check("nothing overflows the viewport", pg.evaluate("""() => {
      const el = document.getElementById('upcomingBlockList');
      return el.scrollWidth > document.documentElement.clientWidth;
    }"""), False)

    # ── Distanse mot mål past 100 %: clamp the bar, never the number (2026-09-11) ───────────
    #
    # Reported live: «169 av 159.4 km · 100%». One clamped figure drove both the bar and the label,
    # so the row stated the overshoot in km and denied it in per cent, in the same line. Exceeding a
    # block's distance target is a good outcome and worth seeing. The Konsistens bar two lines below
    # already had it right — clamped width, raw score in the label.
    print("== distanse mot mål past the target ==")

    def block_hero(target_km):
        pg.goto(APP)
        pg.evaluate("""t => {
          const run = (dato, distanse) => ({ id:dato, dato, uke:'2026-30', oktnavn:'Tur',
            okttype:'Easy', treningsplan:'Runna', løpetype:'utendors', distanse,
            varighet: distanse*360, tempo:360, soner:[0,0,0,0,0] });
          localStorage.setItem('lpl_cache', JSON.stringify({
            sessions: [run('2026-07-20',6), run('2026-07-27',8), run('2026-08-03',7)],
            shoes: [], goals: {}, plannedSessions: [], settings: { zones: [] },
            events: [{ id:'p1', type:'plan', title:'Runna 5K', date:'2026-07-06',
                       endDate:'2026-09-13', targetTotalKm: t }],
            lastUpdated: '' }));
        }""", target_km)
        pg.goto(APP)
        pg.evaluate("() => switchTab('dash')")
        pg.wait_for_timeout(500)
        return pg.evaluate("""() => {
          const label = [...document.querySelectorAll('#blocksCard span')]
            .find(s => / km · \\d+%$/.test(s.textContent.trim()));
          if (!label) return { label: null, width: null };
          const wrap = label.closest('div').parentElement;      // row → the block that owns the bar
          const fill = wrap.children[1].firstElementChild;
          return { label: label.textContent.trim(), width: fill.style.width };
        }""")

    # Control FIRST: 21 km against a 30 km target — nothing clamped, label and bar agree.
    under = block_hero(30)
    check("under target, the label is the real figure", under['label'], '21 av 30 km · 70%')
    check("...and the bar matches it", under['width'], '70%')

    over = block_hero(15)                                       # 21 of 15 km = 140 %
    check("over target, the label passes 100", over['label'], '21 av 15 km · 140%')
    check("...but the bar stops at its track", over['width'], '100%')

    # ── The km targets are decimals, and must declare it (2026-09-11) ──────────────────────
    #
    # A Runna plan total is 346.6 km, not 347. Both km fields carried min="1" and no step, so step
    # defaulted to 1 and a correct decimal was :invalid by the field's own declaration — harmless
    # only because nothing in Planlegging calls checkValidity() yet, which is exactly the kind of
    # latent mismatch that surfaces the day validation is extended. `Distanse (km)` beside them
    # already declared step="0.1".
    #
    # Typed with a COMMA on purpose: this is the second panel for the WebKit comma fix (`df83cde`),
    # and this suite runs on WebKit. Before it, 346,6 here became 3466 — a 10× block target.
    print("== the km targets accept the decimals they are given ==")
    pg.evaluate("() => switchTab('plan')")
    pg.wait_for_timeout(300)
    pg.select_option("#newEvtType", "plan")
    pg.wait_for_timeout(200)

    def typed(sel, keys):
        pg.fill(sel, "")
        pg.click(sel)
        pg.keyboard.type(keys)
        return pg.evaluate("""s => { const e = document.querySelector(s);
          return { value: e.value, valid: e.checkValidity(), num: e.valueAsNumber }; }""", sel)

    tot = typed("#newEvtTotalKmTarget", "346,6")
    check("a comma becomes a point here too", tot['value'], '346.6')
    check("...and 346.6 is a valid total", tot['valid'], True)
    check("...worth 346.6 to the save path", tot['num'], 346.6)
    wk = typed("#newEvtKmTarget", "36,5")
    check("km/uke takes a decimal as well", (wk['value'], wk['valid']), ('36.5', True))
    # Controls: a whole number is still fine, and the floor still bites.
    check("a whole number is still valid", typed("#newEvtTotalKmTarget", "347")['valid'], True)
    check("below min is still refused", typed("#newEvtTotalKmTarget", "0")['valid'], False)
    # økter/uke is deliberately NOT given a step — you cannot run half a session.
    check("økter/uke stays whole-numbered", typed("#newEvtRunTarget", "4,5")['valid'], False)

    # ── A block that has not started judges nothing (2026-09-11) ───────────────────────────
    #
    # The drill-down's isCurrent tested only the END date, so a block starting next Monday read as
    # «Pågår», dated «14.09.2026 – nå», and scored Konsistens «Dårlig 0%» — a verdict on nine weeks
    # that have not happened. The dashboard hero used the correct two-sided test, so the two
    # surfaces disagreed about the same block.
    #
    # ⚠️ Controls included: a CURRENT block must keep every one of these sections, or "the future
    # block hides them" would pass just as well for a panel that renders nothing at all.
    print("== a future block makes no claims ==")

    def panel(start, end):
        pg.goto(APP)
        pg.evaluate("""cfg => {
          const run = (dato, distanse) => ({ id:dato, dato, uke:'2026-30', oktnavn:'Tur',
            okttype:'Easy', treningsplan:'Runna', løpetype:'utendors', distanse,
            varighet: distanse*360, tempo:360, soner:[0,600,600,0,0] });
          localStorage.setItem('lpl_cache', JSON.stringify({
            sessions: [run('2026-08-11',6), run('2026-08-13',8)],
            shoes: [], goals: {}, plannedSessions: [], settings: { zones: [] },
            events: [{ id:'pX', type:'plan', title:'Blokk', date:cfg.s, endDate:cfg.e }],
            lastUpdated: '' }));
        }""", {"s": start, "e": end})
        pg.goto(APP)
        pg.evaluate("() => switchTab('dash')")
        pg.wait_for_timeout(500)
        pg.evaluate("""() => {
          const b = cachedBlocks.find(x => x.title === 'Blokk');
          DetailPanel.openBlock(JSON.parse(JSON.stringify(b)));
        }""")
        pg.wait_for_timeout(300)
        txt = " ".join(pg.inner_text("#detailBody").split())
        pg.evaluate("() => DetailPanel.close()")
        pg.wait_for_timeout(150)
        return txt

    # Control FIRST: a live block still shows everything.
    live = panel("2026-08-10", "2026-10-01")
    check("a live block says Pågår", "Pågår" in live, True)
    # ⚠️ UPPERCASE: .dp-section-label is text-transform:uppercase and inner_text() returns what is
    # RENDERED. Matching "Konsistens" never matched anything, so the future-block assertions below
    # would have passed with the section still present. The controls are what exposed that.
    check("...and scores consistency", "KONSISTENS" in live, True)
    check("...and shows its zone split", "SONEFORDELING" in live, True)

    fut = panel("2026-09-14", "2026-11-19")          # starts after the frozen 2026-08-18
    check("a future block does NOT say Pågår", "Pågår" in fut, False)
    check("...it says Kommende", "Kommende" in fut, True)
    check("...names its real end date, not 'nå'", "19.11.2026" in fut, True)
    check("...passes no consistency verdict", "KONSISTENS" in fut, False)
    check("...and none of its labels leak", "Dårlig" in fut, False)
    check("...claims no missing zone data", "SONEFORDELING" in fut, False)
    check("...and no 'ingen sonedata' orphan", "Ingen sonedata" in fut, False)

    check("no page errors", errs, [])
    b.close()

print(f"\n{passed}/{passed+failed} passed" + ("" if not failed else f"  ({failed} FAILED)"))
sys.exit(1 if failed else 0)
