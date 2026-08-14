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
    b.close()

print(f"\n{passed}/{passed+failed} passed" + ("" if not failed else f"  ({failed} FAILED)"))
sys.exit(1 if failed else 0)
