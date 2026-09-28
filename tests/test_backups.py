"""Lokale sikkerhetskopier — a backup that did not land must never look like one that did.  (2026-09-28)

Standalone — NOT part of run_all.py, which is the fast no-browser gate. Run directly:
    python tests/test_backups.py                    (WebKit, as CI runs it)
    PW_ENGINE=firefox python tests/test_backups.py  (also chromium; firefox is his main browser)

Ported from the template's 2026-09-25 audit (its idbRun), adapted to Puls. What BackupDB did:
  * a transaction that aborted after its write request had succeeded (the shape of a quota failure
    at commit) left save() waiting forever — and «Analyser alle» and the Strava link-apply await it,
    so their buttons stayed dead until a reload;
  * every other failure was swallowed by `catch { /* ignore */ }`, so a backup that never landed
    looked saved — including the snapshot taken right before «Tøm alle data»;
  * a request error was never prevented, which Firefox reports as an uncaught page error;
  * a failed READ of the list rendered «Ingen sikkerhetskopier ennå» — an empty state that lies;
  * the trim ran in its own transaction after the write, so a failure part-way through it left a
    half-trimmed ring.
HANDOFF P3.9 (2026-07-09) had left the swallowing as-is; he reversed that on 2026-09-28: a failed
write is shown, and the three actions that already snapshot first (Tøm alle data, the Strava
link-apply, «Analyser alle») stop instead of running without their safety net. Ordinary saves and
loads are never blocked.

Failures are INJECTED by stubbing IDBObjectStore.prototype, each stub undone before the next check.
Every IndexedDB read the checks compare goes through a raw connection, never through BackupDB, so a
broken BackupDB cannot vouch for itself. Synthetic sessions only, nothing personal.
"""
import json, os, pathlib, sys
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

ENGINE = os.environ.get("PW_ENGINE", "webkit")
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


def skip(name, why):
    print(f"  SKIP {name} ({why})")


# Four runs linked to Strava (so «Analyser alle» has work) and one that is not (so the link-apply has
# something to link). isoWeek is the app's own — read from the page, never re-derived here.
SEED = """() => {
  const run = (id, dato, stravaId) => Object.assign({ id, dato, uke: isoWeek(dato), oktnavn: 'Tur',
    okttype: 'Easy', treningsplan: 'Runna', løpetype: 'utendors', distanse: 8, varighet: 2880,
    tempo: 360, soner: [0, 600, 1200, 0, 0] }, stravaId ? { stravaId } : {});
  localStorage.setItem('lpl_cache', JSON.stringify({
    sessions: [run('a', '2026-09-20', 's1'), run('b', '2026-09-22', 's2'), run('c', '2026-09-24', 's3'),
               run('d', '2026-09-26', null)],
    shoes: [], shoeDefaults: {}, goals: {}, events: [], plannedSessions: [],
    settings: { zones: [] }, lastUpdated: '' }));
}"""

# Failure injection. `constraint` turns the write into add() on a key that exists → a real,
# asynchronous ConstraintError. `abort-after` aborts once the write request has SUCCEEDED, which is
# how a commit-time failure (quota) looks: no request error, only the transaction's abort.
STUB = """(kind) => {
  const P = IDBObjectStore.prototype;
  window.__orig = window.__orig || { put: P.put, getAll: P.getAll, delete: P.delete, getAllKeys: P.getAllKeys };
  const o = window.__orig;
  if (kind === 'constraint') P.put = function (v, k) { return this.add(v, k); };
  if (kind === 'abort-after') P.put = function (...a) {
    const r = o.put.apply(this, a), tx = this.transaction;
    r.addEventListener('success', () => { try { tx.abort(); } catch (_) {} });
    return r; };
  // The LAST request of a save (the trim's key read, when there is nothing to trim) succeeds, and only
  // then the transaction aborts: no request is left to hear it, so only tx.onabort can — the true
  // shape of a quota failure at commit, and the case that used to hang.
  if (kind === 'abort-at-commit') P.getAllKeys = function (...a) {
    const r = o.getAllKeys.apply(this, a), tx = this.transaction;
    r.addEventListener('success', () => { try { tx.abort(); } catch (_) {} });
    return r; };
  if (kind === 'abort-pending') P.put = function (...a) {
    const r = o.put.apply(this, a);
    try { this.transaction.abort(); } catch (_) {}
    return r; };
  if (kind === 'read-fails') P.getAll = function () { throw new DOMException('Lesing feilet (test)', 'UnknownError'); };
  if (kind === 'second-delete-throws') { let n = 0; P.delete = function (...a) {
    if (++n === 2) throw new DOMException('Sletting feilet (test)', 'UnknownError');
    return o.delete.apply(this, a); }; }
}"""
UNSTUB = """() => { const P = IDBObjectStore.prototype, o = window.__orig;
  if (o) { P.put = o.put; P.getAll = o.getAll; P.delete = o.delete; P.getAllKeys = o.getAllKeys; } }"""

# How a save ends — or that it never does. A hang reads as 'hung' after `ms`, never as a pass.
SETTLE = """async (ms) => Promise.race([
  BackupDB.save(Store.toJSON(), Store.data.sessions.length)
    .then(() => 'resolved', e => 'rejected:' + ((e && e.name) || String(e))),
  new Promise(r => setTimeout(() => r('hung'), ms)) ])"""

# Every stored record, read through a raw connection with the ORIGINAL getAll.
RAW = """async () => new Promise((res, rej) => {
  const P = IDBObjectStore.prototype, getAll = (window.__orig && window.__orig.getAll) || P.getAll;
  const r = indexedDB.open('lpl_backups');
  r.onerror = () => rej(r.error);
  r.onsuccess = () => { const db = r.result;
    const q = getAll.call(db.transaction('backups').objectStore('backups'));
    q.onsuccess = () => { res(JSON.stringify(q.result)); db.close(); };
    q.onerror = () => { rej(q.error); db.close(); }; };
})"""

# Old daily copies, written through a raw connection (9 of them + today's = 10, so a save trims 3).
SEED_OLD = """async () => new Promise((res, rej) => {
  const r = indexedDB.open('lpl_backups');
  r.onerror = () => rej(r.error);
  r.onsuccess = () => { const db = r.result, tx = db.transaction('backups', 'readwrite');
    for (let d = 1; d <= 9; d++) { const date = '2026-09-0' + d;
      tx.objectStore('backups').put({ date, timestamp: date + 'T08:00:00.000Z', sessionCount: d, json: '{}' }, date); }
    tx.oncomplete = () => { db.close(); res(); };
    tx.onerror = () => { db.close(); rej(tx.error); }; };
})"""

CARD = "() => (document.getElementById('backupList') || {}).textContent || ''"

with sync_playwright() as pw:
    b = getattr(pw, ENGINE).launch()
    print(f"engine: {ENGINE}")
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    errs, dialogs = [], []
    pg.on("pageerror", lambda e: errs.append(str(e)))

    def on_dialog(d):
        dialogs.append(d.message)
        d.accept()
    pg.on("dialog", on_dialog)
    pg.goto(APP); pg.evaluate(SEED); pg.goto(APP)
    pg.wait_for_timeout(800)

    print("== control: the startup load wrote today's copy ==")
    raw = pg.evaluate(RAW)
    check("control: one record, today's", [r.get("date") for r in json.loads(raw)],
          [pg.evaluate("() => localISODate()")])
    check("control: no backup failure recorded yet", pg.evaluate("() => !BackupDB.lastError"), True)

    print("== a failed write is a failure: it rejects, it never hangs, it never looks saved ==")
    pg.evaluate(STUB, "abort-at-commit")
    check("aborted at commit, after every request succeeded (a quota failure) → rejects, does not hang",
          pg.evaluate(SETTLE, 2500), "rejected:AbortError")
    pg.evaluate(UNSTUB)
    pg.evaluate(STUB, "abort-after")
    check("aborted after the write succeeded, with the trim still pending → rejects with AbortError",
          pg.evaluate(SETTLE, 2500), "rejected:AbortError")
    pg.evaluate(UNSTUB)
    pg.evaluate(STUB, "abort-pending")
    # Here the NEXT request of the same save (the trim's key read) meets the aborted transaction first,
    # so the reason is TransactionInactiveError — true, just not the abort's own name. What matters:
    # a named rejection, never success and never a hang. (The realistic commit-time abort above and a
    # real request error below keep their exact names.)
    out = pg.evaluate(SETTLE, 2500)
    check("aborted with the write still pending → rejects with a named error",
          (out.startswith("rejected:"), out not in ("rejected:null", "rejected:undefined")), (True, True))
    pg.evaluate(UNSTUB)

    before = pg.evaluate(RAW)
    pg.evaluate(STUB, "constraint")
    check("a request error (ConstraintError) → rejects WITH THAT ERROR, not null, not success",
          pg.evaluate(SETTLE, 2500), "rejected:ConstraintError")
    pg.evaluate(UNSTUB)
    check("...and nothing was written (the transaction aborted)", pg.evaluate(RAW) == before, True)
    # The template's audit saw Firefox report an UNPREVENTED request error as an uncaught page error,
    # so the handler calls preventDefault(). Probed 2026-09-28 in Playwright 1.61's Firefox, with and
    # without a transaction error handler: it reports nothing at all (no console message, no page
    # error), so no check here can fail on the old code. Not counted as a pass — a check that cannot
    # fail proves nothing (the vacuous-check catalogue).
    skip("...and Firefox reports no uncaught error for it",
         "not observable in Playwright's Firefox; preventDefault() kept per the template's finding")

    print("== the card says so, and only a successful WRITE takes the warning down ==")
    pg.evaluate("() => switchTab('settings')")
    pg.wait_for_timeout(300)
    pg.evaluate("async () => { await Settings.renderBackupList(); }")
    check("Innstillinger shows «Siste sikkerhetskopi feilet»", "Siste sikkerhetskopi feilet" in pg.evaluate(CARD), True)
    pg.evaluate("async () => { await BackupDB.getAll(); await Settings.renderBackupList(); }")
    check("...a successful read does not clear it", "Siste sikkerhetskopi feilet" in pg.evaluate(CARD), True)
    pg.evaluate("async () => { await BackupDB.restore(localISODate()); await Settings.renderBackupList(); }")
    check("...nor does a restore read", "Siste sikkerhetskopi feilet" in pg.evaluate(CARD), True)
    check("...the next successful write resolves", pg.evaluate(SETTLE, 2500), "resolved")
    pg.evaluate("async () => { await Settings.renderBackupList(); }")
    check("...and takes the warning down", "Siste sikkerhetskopi feilet" in pg.evaluate(CARD), False)

    print("== a list that cannot be read is not an empty list ==")
    before = pg.evaluate(RAW)
    pg.evaluate(STUB, "read-fails")
    pg.evaluate("async () => { try { await Settings.renderBackupList(); } catch (_) {} }")
    card = pg.evaluate(CARD)
    pg.evaluate(UNSTUB)
    check("a failed read says «Kunne ikke lese sikkerhetskopiene»", "Kunne ikke lese sikkerhetskopiene" in card, True)
    check("...and never «Ingen sikkerhetskopier ennå»", "Ingen sikkerhetskopier ennå" in card, False)
    check("...and every stored record is byte-identical", pg.evaluate(RAW) == before, True)

    print("== the trim is all-or-nothing ==")
    pg.evaluate(SEED_OLD)
    before = pg.evaluate(RAW)
    check("control: 9 old copies + today's = 10 records to trim from", len(json.loads(before)), 10)
    pg.evaluate(STUB, "second-delete-throws")
    check("a delete failing part-way through the trim → the save rejects", pg.evaluate(SETTLE, 2500),
          "rejected:UnknownError")
    pg.evaluate(UNSTUB)
    check("...and nothing is written or deleted", pg.evaluate(RAW) == before, True)
    check("control: without the stub the same save trims to 7", (pg.evaluate(SETTLE, 2500),
          len(json.loads(pg.evaluate(RAW)))), ("resolved", 7))

    print("== «Analyser alle» does not run without its safety copy ==")
    pg.evaluate("""() => { StravaIO.isSignedIn = () => true; window.__analyzed = 0;
      Continuity._analyzeInto = async () => { window.__analyzed++; return 'ok'; }; }""")
    pg.evaluate(STUB, "constraint")
    out = pg.evaluate("""async () => Promise.race([Continuity.analyzeAll().then(() => 'returned', e => 'threw:' + e.name),
      new Promise(r => setTimeout(() => r('hung'), 3000))])""")
    pg.evaluate(UNSTUB)
    state = pg.evaluate("""() => ({ analysed: window.__analyzed, running: Continuity._backfillRunning,
      btnDisabled: document.getElementById('contBackfillBtn').disabled,
      msg: document.getElementById('contBackfillMsg').textContent })""")
    check("«Analyser alle» returns (neither hangs nor throws)", out, "returned")
    check("...having analysed nothing", state.get("analysed"), 0)
    check("...its button and running flag are released", (state.get("running"), state.get("btnDisabled")), (False, False))
    check("...and it says why (a message naming the backup)", "sikkerhetskopi" in (state.get("msg") or ""), True)

    print("== the Strava link-apply does not run without its safety copy ==")
    pg.evaluate("""() => { StravaBackfill.proposed = [{ sessionId: 'd', activityId: 999 }];
      document.getElementById('backfillBody').innerHTML = '<input type="checkbox" checked data-i="0">'; }""")
    pg.evaluate(STUB, "constraint")
    out = pg.evaluate("""async () => Promise.race([StravaBackfill.apply().then(() => 'returned', e => 'threw:' + e.name),
      new Promise(r => setTimeout(() => r('hung'), 3000))])""")
    pg.evaluate(UNSTUB)
    state = pg.evaluate("""() => ({ linked: (Store.data.sessions.find(s => s.id === 'd') || {}).stravaId || null,
      applying: StravaBackfill._applying,
      toast: [...document.querySelectorAll('.toast-error')].map(t => t.textContent).join(' | ') })""")
    check("the link-apply returns (neither hangs nor throws)", out, "returned")
    check("...having linked nothing", state.get("linked"), None)
    check("...its double-click guard is released", state.get("applying"), False)
    check("...and it says why (an error toast naming the backup)", "sikkerhetskopi" in (state.get("toast") or ""), True)

    print("== ordinary saves and loads are never blocked by a failing backup ==")
    pg.evaluate(STUB, "constraint")
    load = pg.evaluate("""async () => { const ok = Store.load(Store.toJSON(), { snapshot: true });
      await new Promise(r => setTimeout(r, 400)); return { ok, n: Store.data.sessions.length }; }""")
    # Judged on the local cache, the one store every engine writes: FileIO.save()'s own return value
    # depends on the engine (Chromium takes the file-picker path, which fails headless with no file
    # handle and no user gesture — nothing to do with backups).
    cached = pg.evaluate("""async () => { Store.data.sessions[0].oktnavn = 'Markør'; await FileIO.save();
      return JSON.parse(localStorage.getItem('lpl_cache')).sessions[0].oktnavn; }""")
    pg.evaluate(UNSTUB)
    check("a load with a failing backup still loads", load, {"ok": True, "n": 4})
    check("an ordinary save with a failing backup still writes the data", cached, "Markør")

    print("== «Tøm alle data» does not delete without its safety copy ==")
    pg.evaluate("() => switchTab('settings')")
    pg.wait_for_timeout(300)
    pg.evaluate(STUB, "constraint")
    dialogs.clear()
    pg.click("#btnClearAll")
    pg.wait_for_timeout(800)
    pg.evaluate(UNSTUB)
    check("every session is still there", pg.evaluate("() => Store.data.sessions.length"), 4)
    check("...and it says so (an alert: nothing was deleted)", any("ingenting er slettet" in m for m in dialogs), True)
    dialogs.clear()
    pg.click("#btnClearAll")
    pg.wait_for_timeout(800)
    check("with a working backup it clears", pg.evaluate("() => Store.data.sessions.length"), 0)
    today = pg.evaluate("() => localISODate()")
    check("...and the copy it waited for holds the 4 sessions",
          next((r.get("sessionCount") for r in json.loads(pg.evaluate(RAW)) if r.get("date") == today), None), 4)

    check("no page errors", errs, [])
    b.close()

print(f"\n{passed}/{passed + failed} passed" + (f"  ({failed} FAILED)" if failed else ""))
sys.exit(1 if failed else 0)
