"""Verify the tab navigation: unchanged on desktop, a fixed bottom bar on phones.  (2026-09-01)

Standalone — NOT part of run_all.py, which is the fast no-browser gate. Run directly:
    python tests/test_nav.py       (needs Playwright + WebKit)

The nav became responsive on 2026-09-01: one `.tabs` element, restyled at ≤600px into a fixed bottom
bar of six slots (Legg til · Oversikt · Logg · Plan · Verktøy · Mer) with Løpeatlas and Innstillinger
behind Mer. There is deliberately NO second mobile nav — switchTab() marks `.tab.active` across every
`.tab`, so a duplicate would be a second source of truth for which tab is current.

Two real bugs were found writing this, both invisible to the eye at a glance:

  1. The bottom-bar rules first went in a SECOND `@media (max-width: 600px)` block higher up the
     sheet. The pre-existing phone block later in the file re-applied the old scrolling-strip padding
     at equal specificity and won, so the bar rendered with 12px side padding and clipped labels.
     Measuring it produced numbers that described the bug rather than the design.
  2. `body:not(.is-dash) .tabs` pins z-index to 101 and outranks a plain `.tabs` rule, so on every
     non-dashboard tab the bar sank beneath the 199 backdrop and the two tabs inside the Mer sheet
     could not be tapped at all.

Both are why this reads geometry and computed styles rather than trusting appearances: is_visible()
answers about LAYOUT, and would have called that unclickable sheet perfectly visible.
"""
import pathlib, sys
sys.stdout.reconfigure(encoding="utf-8")   # æøå in the labels
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


with sync_playwright() as p:
    b = p.webkit.launch()

    # ── Desktop is untouched ─────────────────────────────────────────────────────────────────────
    # Grouping Løpeatlas + Innstillinger into `.tabs-more` changed the DOM order, so the desktop
    # order is pinned by `order:` in CSS. That pin is the thing most likely to rot silently.
    print("== desktop 1280px ==")
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    derr = []
    pg.on("pageerror", lambda e: derr.append(str(e)))
    pg.goto(APP)
    pg.wait_for_timeout(300)

    check("visual order matches the original",
          pg.evaluate("""() => [...document.querySelectorAll('.tab')]
              .map(t => ({ tab: t.dataset.tab, x: Math.round(t.getBoundingClientRect().x) }))
              .sort((a, b) => a.x - b.x).map(t => t.tab)"""),
          ["form", "dash", "log", "atlas", "plan", "tools", "settings"])
    check("full labels shown, bottom-bar labels hidden",
          pg.evaluate("""() => {
            const t = document.querySelector('.tab[data-tab="log"]');
            return [getComputedStyle(t.querySelector('.t-lbl')).display,
                    getComputedStyle(t.querySelector('.t-short')).display].join('/'); }"""),
          "inline/none")
    # The labels themselves are the contract with the user — a refactor must not quietly reword them.
    check("label text unchanged",
          pg.evaluate("""() => [...document.querySelectorAll('.tab .t-lbl')].map(e => e.textContent).join('|')"""),
          "Legg til økt|Oversikt|Treningslogg|Planlegging|Verktøy|Løpeatlas|Innstillinger")
    check("Mer button is phone-only",
          pg.evaluate("() => getComputedStyle(document.getElementById('tabMoreBtn')).display"), "none")
    check(".tabs-more is transparent to desktop layout",
          pg.evaluate("() => getComputedStyle(document.getElementById('tabsMore')).display"), "contents")
    # sticky, not fixed: pinned under the header since long before this change. The point is that the
    # phone rules have not leaked upward.
    check("strip still sticky at the top, not fixed to the bottom",
          pg.evaluate("() => getComputedStyle(document.querySelector('.tabs')).position"), "sticky")
    check("no desktop page errors", derr, [])
    pg.close()

    # ── Phone: the bar, the sheet, and every close path ──────────────────────────────────────────
    print("== phone 402px ==")
    pg = b.new_page(viewport={"width": 402, "height": 844})
    merr = []
    pg.on("pageerror", lambda e: merr.append(str(e)))
    pg.goto(APP)
    pg.wait_for_timeout(300)
    sheet = lambda: pg.evaluate("() => getComputedStyle(document.getElementById('tabsMore')).display")

    bar = pg.evaluate("""() => {
      const t = document.querySelector('.tabs'), r = t.getBoundingClientRect();
      return { pos: getComputedStyle(t).position, bottom: Math.round(r.bottom),
               z: +getComputedStyle(t).zIndex, fits: t.scrollWidth <= t.clientWidth + 1 }; }""")
    check("bar is fixed to the bottom edge", (bar["pos"], bar["bottom"]), ("fixed", 844))
    check("...and does not overflow sideways", bar["fits"], True)
    # The z-index bug above: 101 put the bar under the backdrop and made the sheet unusable.
    check("...and outranks the 199 backdrop", bar["z"] > 199, True)

    # ⚠️ Sorted by X, not by DOM order. The first version of this check read querySelectorAll order
    # and passed while Mer rendered FIRST on screen — `.tab-more-btn` had no `order:` so it defaulted
    # to 0 and sorted ahead of every tab. DOM order is not visual order the moment `order:` exists,
    # and a check that conflates them tests nothing that a user can see.
    slots = pg.evaluate("""() => [...document.querySelectorAll('.tabs > .tab, .tab-more-btn')]
        .filter(e => getComputedStyle(e).display !== 'none')
        .map(e => ({ tab: e.dataset.tab || 'mer', x: e.getBoundingClientRect().x }))
        .sort((a, b) => a.x - b.x).map(e => e.tab)""")
    check("six slots, left to right, Mer last", slots, ["form", "dash", "log", "plan", "tools", "mer"])

    # Every slot must clear the 44x44 tap minimum, and no label may be cut off. Measured, because
    # "looks fine" is exactly what the overridden-CSS version also looked like.
    geo = pg.evaluate("""() => [...document.querySelectorAll('.tabs > .tab, .tab-more-btn')]
        .filter(e => getComputedStyle(e).display !== 'none').map(e => {
          const r = e.getBoundingClientRect(), l = e.querySelector('.t-short');
          return { tab: e.dataset.tab || 'mer', w: Math.round(r.width), h: Math.round(r.height),
                   clipped: l ? l.scrollWidth > l.clientWidth + 1 : false }; })""")
    check("every slot clears the 44px tap target",
          [g["tab"] for g in geo if g["w"] < 44 or g["h"] < 44], [])
    check("no bottom-bar label is clipped",
          [g["tab"] for g in geo if g["clipped"]], [])

    check("sheet starts closed", sheet(), "none")
    pg.click("#tabMoreBtn")
    pg.wait_for_timeout(200)
    check("Mer opens the sheet", sheet(), "block")
    check("aria-expanded tracks the state", pg.get_attribute("#tabMoreBtn", "aria-expanded"), "true")
    check("sheet holds exactly the two overflow tabs",
          pg.evaluate("() => [...document.querySelectorAll('#tabsMore .tab')].map(t => t.dataset.tab)"),
          ["atlas", "settings"])
    # Positive control: display:block alone would pass even if the sheet sat off-screen or at zero
    # width — the failure mode this whole file exists to catch.
    check("...and is really on screen, above the bar",
          pg.evaluate("""() => { const r = document.getElementById('tabsMore').getBoundingClientRect();
              return r.width > 100 && r.top > 0 && r.bottom < 844; }"""), True)

    # The case that matters: tapping a tab INSIDE the sheet must switch panel and clear the sheet,
    # or the sheet stays sitting over the panel it just opened.
    pg.click("#tabsMore .tab[data-tab='atlas']")
    pg.wait_for_timeout(300)
    check("choosing a sheet tab switches panel",
          pg.evaluate("() => document.querySelector('.panel.active').id"), "panel-atlas")
    check("...and closes the sheet", sheet(), "none")

    pg.click("#tabMoreBtn"); pg.wait_for_timeout(150)
    pg.click("#moreBackdrop", force=True); pg.wait_for_timeout(200)
    check("backdrop closes it", sheet(), "none")

    pg.click("#tabMoreBtn"); pg.wait_for_timeout(150)
    pg.keyboard.press("Escape"); pg.wait_for_timeout(200)
    check("Escape closes it", sheet(), "none")

    check("content clears the fixed bar",
          pg.evaluate("""() => parseInt(getComputedStyle(
              document.querySelector('.panel.active')).paddingBottom, 10) >= 60"""), True)
    check("no mobile page errors", merr, [])
    pg.close()

    b.close()

print(f"\n{passed}/{passed+failed} passed" + ("" if not failed else f"  ({failed} FAILED)"))
sys.exit(1 if failed else 0)
