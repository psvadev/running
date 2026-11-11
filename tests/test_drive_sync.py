"""Google Drive sync — what a save promises when the tab dies, and what a conflict asks.  (2026-11-11)

Standalone — NOT part of run_all.py, which is the fast no-browser gate. Run directly:
    python tests/test_drive_sync.py                    (WebKit, as CI runs it)
    PW_ENGINE=firefox python tests/test_drive_sync.py  (also chromium; firefox is his main browser)

Drive is his real setup on both devices, and until this suite no test ever signed in to it: every
DriveIO regression shipped green (the 2026-11-11 audit, TG-2). The page is served over https (as
Pages serves it) and Google Drive is a FAKE answered in-process: `ctx.route` serves the file's
metadata, its body and every upload, and can HOLD an upload so it never finishes — the state of a
tab closed, or discarded by iOS, mid-save. Tokens are synthetic and never leave the test.

What it pins (the audit's findings; each was red on the code before the fix):
  * DS-1 — a save still uploading when the tab dies must leave «Drive is behind» on disk: the
    reopened tab asks instead of quietly applying Drive's older copy over the edit. Two overlapping
    saves: the first finishing must not mark the second's edits as synced.
  * DS-2 — the conflict check compares like with like: identical data is NOT a conflict (it used to
    compare compact JSON with indented JSON, never equal). A real conflict names both counts, and the
    side about to be discarded is copied to «før endring» first; a copy that fails changes nothing.
  * DS-6 — a load is confirmed only once Drive's BODY has arrived; a save before that is 'blocked'.
Backups are read through a raw IndexedDB connection, never through BackupDB, so a broken BackupDB
cannot vouch for itself. Synthetic sessions only, nothing personal.
"""
import json, os, pathlib, re, sys
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

ENGINE = os.environ.get("PW_ENGINE", "webkit")
ROOT = pathlib.Path(__file__).resolve().parent.parent
HTML = (ROOT / "puls.html").read_text(encoding="utf-8")
URL = "https://puls.test/running/puls.html"
BEFORE = "før-endring"
passed = failed = 0


def check(name, got, want):
    global passed, failed
    if got == want:
        passed += 1
        print(f"  PASS {name}")
    else:
        failed += 1
        print(f"  FAIL {name}\n       got  {got!r}\n       want {want!r}")


CORS = {"access-control-allow-origin": "*", "access-control-allow-headers": "authorization,content-type",
        "access-control-allow-methods": "GET,PATCH,POST,OPTIONS", "content-type": "application/json"}


class FakeDrive:
    """One puls.json, id f1. `hold` parks every upload until release() — a save that never finishes."""
    def __init__(self, data):
        self.body = json.dumps(data, ensure_ascii=False, indent=2)
        self.n = 0
        self.hold = False
        self.held = []
        self.media_gets = 0
        self.patches = 0
        self.revoked = []

    @property
    def modified(self):
        return f"2026-11-01T10:00:{self.n:02d}.000Z"

    def sessions(self):
        return len(json.loads(self.body)["sessions"])

    def other_device_writes(self, data):
        """Another device saved: new content, new modifiedTime."""
        self.body = json.dumps(data, ensure_ascii=False, indent=2)
        self.n += 1

    def _patch(self, route):
        self.body = route.request.post_data
        self.n += 1
        self.patches += 1
        route.fulfill(status=200, headers=CORS, body=json.dumps({"modifiedTime": self.modified}))

    def release(self):
        route = self.held.pop(0)
        try:
            self._patch(route)
        except Exception:
            pass                                    # its page is gone — exactly the case being tested

    def handle(self, route):
        req = route.request
        if req.method == "OPTIONS":
            return route.fulfill(status=204, headers=CORS)
        if "/upload/drive/v3/files/f1" in req.url and req.method == "PATCH":
            if self.hold:
                self.held.append(route)
                return
            return self._patch(route)
        if "/drive/v3/files/f1" in req.url and "alt=media" in req.url:
            self.media_gets += 1
            return route.fulfill(status=200, headers=CORS, body=self.body)
        if "/drive/v3/files/f1" in req.url and "fields=modifiedTime" in req.url:
            return route.fulfill(status=200, headers=CORS, body=json.dumps({"modifiedTime": self.modified}))
        route.fulfill(status=404, headers=CORS, body="{}")


def run(i, dato):
    return {"id": f"s{i}", "dato": dato, "uke": "2026-44", "oktnavn": "Tur", "okttype": "Easy",
            "treningsplan": "Egentrening", "løpetype": "utendors", "distanse": 8, "varighet": 2880,
            "tempo": 360, "soner": [0, 600, 1200, 0, 0]}


def dataset(n):
    return {"sessions": [run(i, f"2026-10-{i + 1:02d}") for i in range(n)], "shoes": [], "shoeDefaults": {},
            "goals": {}, "events": [], "plannedSessions": [], "settings": {"zones": []},
            "lastUpdated": "2026-10-31T12:00:00.000Z"}


N = 5
NEW_RUN = "(id) => Store.addSession({ ...Store.data.sessions[0], id, dato: '2026-10-30', oktnavn: 'Ny økt' })"
# A Drive body whose json() resolves only after a delay, when the test asks for it — the window
# between Drive answering and its body arriving (DS-6). Everything else passes through untouched.
SLOW_BODY = """
(() => {
  const orig = window.fetch;
  window.fetch = async (...a) => {
    const res = await orig(...a);
    if (String(a[0]).includes('alt=media') && localStorage.getItem('test_slowBody')) {
      const json = res.json.bind(res);
      res.json = () => new Promise(r => setTimeout(() => r(json()), 2500));
    }
    return res;
  };
})();
"""
READ_BEFORE = """() => new Promise((res, rej) => {
  const r = indexedDB.open('lpl_backups');
  r.onerror = () => rej(r.error);
  r.onsuccess = () => {
    const db = r.result;
    if (!db.objectStoreNames.contains('backups')) { db.close(); return res(null); }
    const g = db.transaction('backups').objectStore('backups').get('""" + BEFORE + """');
    g.onsuccess = () => { db.close(); const v = g.result;
      res(v ? { reason: v.reason, count: v.sessionCount, inJson: JSON.parse(v.json).sessions.length } : null); };
    g.onerror = () => { db.close(); rej(g.error); };
  };
})"""
PENDING = "() => localStorage.getItem('pulsDrivePendingLocal')"


def setup(p, browser):
    """A fresh profile signed in to the fake Drive, booted once so Drive holds the app's own
    serialisation of N sessions (exactly what a real device leaves there). → (ctx, page, drive, dialogs)"""
    drive = FakeDrive(dataset(N))
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    ctx.add_init_script(SLOW_BODY)
    ctx.route(re.compile(r"^https://www\.googleapis\.com/"), drive.handle)
    def oauth(r):
        if r.request.method != "OPTIONS" and "/revoke" in r.request.url:
            drive.revoked.append((r.request.url, r.request.post_data or ""))
        r.fulfill(status=200, headers=CORS, body="[]")
    ctx.route(re.compile(r"^https://(oauth2\.googleapis\.com|api\.github\.com)/"), oauth)
    ctx.route("https://puls.test/**", lambda r: r.fulfill(
        status=200, body=HTML, headers={"content-type": "text/html; charset=utf-8"}))
    dialogs = []
    pg = open_page(ctx, dialogs)
    pg.evaluate("""(d) => {
      localStorage.setItem('lpl_cache', JSON.stringify(d));
      localStorage.setItem('pulsDriveToken', JSON.stringify({ access_token: 'test-a', refresh_token: 'test-r',
                                                              expires_at: Date.now() + 3600e3 }));
      localStorage.setItem('pulsDriveFileId', 'f1');
      localStorage.setItem('pulsDriveConnected', '1');
      localStorage.setItem('pulsDriveClientId', 'test-client');
      localStorage.setItem('pulsDriveSecret', 'test-secret');
    }""", dataset(N))
    pg.reload()
    settle(pg)
    pg.evaluate("() => FileIO.save()")          # Drive now holds what this app writes
    pg.wait_for_timeout(600)
    return ctx, pg, drive, dialogs


def open_page(ctx, dialogs, answer=True):
    pg = ctx.new_page()
    pg.on("dialog", lambda d: (dialogs.append(d.message), d.accept() if answer else d.dismiss()))
    pg.goto(URL)
    return pg


def settle(pg, ms=1200):
    pg.wait_for_function("() => typeof Store !== 'undefined' && typeof DriveIO !== 'undefined'", timeout=30000)
    pg.wait_for_timeout(ms)


def reopen(ctx, dialogs, answer=True):
    pg = open_page(ctx, dialogs, answer)
    settle(pg)
    return pg


def leave_unsynced(pg, drive, sid):
    """Add a session, let its upload start, and close the tab before Drive ever answers."""
    drive.hold = True
    pg.evaluate(NEW_RUN, sid)
    pg.wait_for_timeout(500)
    held = len(drive.held)
    pending = pg.evaluate(PENDING)
    pg.close()
    drive.hold = False
    for route in drive.held:                    # the tab is gone: nothing in it can see this answer —
        try:                                    # it only stops Playwright reporting a dangling route
            route.abort()
        except Exception:
            pass
    drive.held.clear()
    return held, pending


with sync_playwright() as p:
    b = getattr(p, ENGINE).launch()
    print(f"engine: {ENGINE}")

    # ── 0. the harness reaches the real code path ────────────────────────────────────────────────
    print("== a signed-in boot ==")
    ctx, pg, drive, dialogs = setup(p, b)
    check("control: the app is signed in to Drive", pg.evaluate("() => DriveIO.isSignedIn()"), True)
    check("control: the boot fetched Drive's body", drive.media_gets >= 1, True)
    check("control: the first save reached Drive", (drive.patches, drive.sessions()), (1, N))
    check("in sync: no dialog, nothing pending", (dialogs, pg.evaluate(PENDING)), ([], None))

    # ── 1. DS-2: identical data is not a conflict ────────────────────────────────────────────────
    print("== DS-2 identical data ==")
    pg.evaluate("() => localStorage.setItem('pulsDrivePendingLocal', '1')")   # e.g. a PATCH whose answer was lost
    pg.close()
    pg = reopen(ctx, dialogs)
    check("control: the reopened tab loaded Drive with the flag set", drive.media_gets >= 2, True)
    check("pending + Drive identical to this device: no dialog", dialogs, [])
    check("...and the flag is cleared", pg.evaluate(PENDING), None)
    check("...and nothing changed", (pg.evaluate("() => Store.data.sessions.length"), drive.sessions()), (N, N))
    pg.close(); ctx.close()

    # ── 2. DS-1: the tab dies mid-upload → the reopened tab asks; OK keeps this device's run ─────
    print("== DS-1 a save that never finishes (OK: keep this device) ==")
    ctx, pg, drive, dialogs = setup(p, b)
    held, pending = leave_unsynced(pg, drive, "nyA")
    check("control: the upload really started and was held", held, 1)
    check("while it uploads, Drive is marked behind (on disk)", pending, "1")
    check("control: Drive still has the old copy", drive.sessions(), N)
    pg = reopen(ctx, dialogs, answer=True)
    check("the reopened tab asks instead of applying Drive's older copy", len(dialogs), 1)
    msg = dialogs[0] if dialogs else ""
    check("...and the question names both counts", f"Drive har {N} økter, denne enheten har {N + 1}" in msg, True)
    check("...and says a copy is taken first", "En kopi tas først" in msg, True)
    pg.wait_for_timeout(800)
    check("OK: the run survived on this device", pg.evaluate("() => Store.data.sessions.some(s => s.id === 'nyA')"), True)
    check("...and reached Drive", drive.sessions(), N + 1)
    check("...and nothing is pending any more", pg.evaluate(PENDING), None)
    check("Drive's discarded copy is in «før endring»", pg.evaluate(READ_BEFORE),
          {"reason": "Drive-konflikt: Drive-versjonen", "count": N, "inJson": N})

    # ── 3. Cancel takes Drive's copy — and keeps this device's first ─────────────────────────────
    print("== DS-2 Cancel: take Drive, this device's copy kept first ==")
    held, pending = leave_unsynced(pg, drive, "nyB")
    check("control: second unsynced save held and marked", (held, pending), (1, "1"))
    dialogs.clear()
    pg = reopen(ctx, dialogs, answer=False)
    check("the reopened tab asks", len(dialogs), 1)
    pg.wait_for_timeout(800)
    check("Cancel: this device now shows Drive's copy",
          (pg.evaluate("() => Store.data.sessions.length"), pg.evaluate("() => Store.data.sessions.some(s => s.id === 'nyB')")),
          (N + 1, False))
    check("...and the discarded local copy is in «før endring»", pg.evaluate(READ_BEFORE),
          {"reason": "Drive-konflikt: denne enheten", "count": N + 2, "inJson": N + 2})
    check("...and nothing is pending", pg.evaluate(PENDING), None)

    # ── 4. A copy that fails changes nothing ─────────────────────────────────────────────────────
    print("== DS-2 no copy, no change ==")
    other = json.loads(drive.body)
    other["sessions"] = other["sessions"][:2]
    drive.other_device_writes(other)                       # another device left Drive with 2 sessions
    pg.evaluate("() => { BackupDB.saveBefore = async () => { throw new Error('test: backup refused'); }; }")
    dialogs.clear()
    pg.evaluate("() => FileIO.save()")                      # preflight sees the other device → conflict
    pg.wait_for_timeout(600)
    check("control: the save saw the other device's write", pg.evaluate(PENDING), "1")
    pg.click("#driveIndicator")                             # «klikk for å løse»
    pg.wait_for_timeout(800)
    check("control: the conflict dialog appeared", any("Både denne enheten og Drive" in m for m in dialogs), True)
    check("a refused copy is said out loud", any("Kunne ikke ta sikkerhetskopi" in m for m in dialogs), True)
    check("...and Drive was not overwritten", drive.sessions(), 2)
    check("...and this device kept its data", pg.evaluate("() => Store.data.sessions.length"), N + 1)
    check("...and the change is still pending", pg.evaluate(PENDING), "1")
    pg.close(); ctx.close()

    # ── 5. DS-1: overlapping saves — the first finishing does not clear the second ───────────────
    print("== DS-1 two saves in flight ==")
    ctx, pg, drive, dialogs = setup(p, b)
    drive.hold = True
    pg.evaluate(NEW_RUN, "olA"); pg.wait_for_timeout(400)
    pg.evaluate(NEW_RUN, "olB"); pg.wait_for_timeout(400)
    check("control: both uploads are in flight", len(drive.held), 2)
    drive.release(); pg.wait_for_timeout(400)
    check("the first one landing leaves Drive marked behind", pg.evaluate(PENDING), "1")
    drive.release(); pg.wait_for_timeout(400)
    drive.hold = False
    check("the last one landing clears it", pg.evaluate(PENDING), None)
    check("...and Drive has both runs", drive.sessions(), N + 2)
    pg.close(); ctx.close()

    # ── 6. DS-6: a save while Drive's body is still arriving is blocked ──────────────────────────
    print("== DS-6 confirmed only once the body has arrived ==")
    ctx, pg, drive, dialogs = setup(p, b)
    pg.evaluate("() => localStorage.setItem('test_slowBody', '1')")
    pg.close()
    pg = open_page(ctx, dialogs)
    pg.wait_for_function("() => typeof DriveIO !== 'undefined'", timeout=30000)
    pg.wait_for_timeout(700)                                # Drive has answered; its body has not arrived
    before = drive.patches
    check("a save before the body arrives is blocked", pg.evaluate("() => DriveIO.save()"), "blocked")
    check("...and uploads nothing", drive.patches, before)
    pg.evaluate("() => localStorage.removeItem('test_slowBody')")
    pg.wait_for_timeout(2600)
    check("control: once it arrives, saving works again", pg.evaluate("() => DriveIO.save()"), True)
    pg.close(); ctx.close()

    # ── SEC-2: «Koble fra» revokes the grant, not an expired access token ──────────────────────────
    # It sent the stored ACCESS token (1 h) as ?token=…; usually expired, refused by Google, the error
    # swallowed — and the refresh token stayed valid. Revoking the REFRESH token ends the whole grant.
    print("== Koble fra Google Drive: the refresh token is revoked ==")
    ctx, pg, drive, dialogs = setup(p, b)
    pg.evaluate("() => DriveIO.disconnect()")
    pg.wait_for_timeout(400)
    check("one revoke, for the refresh token, in the body — no token in the URL",
          [(u.split("?")[0], d, "?" in u) for u, d in drive.revoked],
          [("https://oauth2.googleapis.com/revoke", "token=test-r", False)])
    check("...and the tokens are forgotten here", pg.evaluate("() => localStorage.getItem('pulsDriveToken')"), None)
    pg.close(); ctx.close()
    b.close()

print(f"\n{passed}/{passed + failed} passed" + (f"  ({failed} FAILED)" if failed else ""))
sys.exit(1 if failed else 0)
