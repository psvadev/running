"""Lokale sikkerhetskopier — what a backup promises, and that a failed one never looks saved.  (2026-09-28)

Standalone — NOT part of run_all.py, which is the fast no-browser gate. Run directly:
    python tests/test_backups.py                    (WebKit, as CI runs it)
    PW_ENGINE=firefox python tests/test_backups.py  (also chromium; firefox is his main browser)

Ported from the template's 2026-09-25 audit (its idbRun and saveDailyBackup), adapted to Puls.

FAILURES (item 1). What BackupDB did: a transaction that aborted after its requests had succeeded
(a quota failure at commit) left save() waiting forever — and «Analyser alle» and the Strava
link-apply await it, so their buttons stayed dead; every other failure was swallowed (`catch {}`),
so a backup that never landed looked saved, including the one taken right before «Tøm alle data»;
a failed READ of the list rendered «Ingen sikkerhetskopier ennå»; the trim ran in its own
transaction, so a failure part-way left a half-trimmed ring. His calls (2026-09-28, reversing HANDOFF
P3.9): a failed write is shown until a later WRITE succeeds; «Tøm alle data», the link-apply and
«Analyser alle» stop when their copy fails; ordinary saves and loads are never blocked.

WHAT A COPY IS (item 2). Today's copy was overwritten by every load and Drive pull, so "today" was
always the latest state and could not undo a mistake made earlier today. Now:
  * the FIRST state seen each LOCAL calendar day is kept, atomically — the "is today there?" read
    and the write share one readwrite transaction, so two callers can't both see "missing";
  * «før endring» is a separate, single-level copy taken right before a bulk change and overwritten
    by the next one; the Strava link-apply and the analysis it starts count as ONE change;
  * a tab left open past midnight takes the new day's copy when it becomes VISIBLE, never hidden.

Failures are INJECTED by stubbing IDBObjectStore.prototype, each stub undone before the next check.
Every IndexedDB read the checks compare goes through a raw connection, never through BackupDB, so a
broken BackupDB cannot vouch for itself. Synthetic sessions only, nothing personal.
"""
import json, os, pathlib, sys
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

ENGINE = os.environ.get("PW_ENGINE", "webkit")
APP = (pathlib.Path(__file__).resolve().parent.parent / "puls.html").as_uri()
BEFORE = "før-endring"
LINK, CLEAR = "Koble gamle økter til Strava", "Tøm alle data"
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

# Failure injection. `constraint` turns a write into add() on a key that exists → a real, asynchronous
# ConstraintError. `abort-at-commit` aborts once the LAST request (the trim's key read, when there is
# nothing to trim) has succeeded: nothing is left to hear it but tx.onabort — a quota failure at
# commit, the case that used to hang. `abort-after` aborts right after the write succeeded, while the
# trim's key read is still pending.
STUB = """(kind) => {
  const P = IDBObjectStore.prototype;
  window.__orig = window.__orig || { put: P.put, get: P.get, getAll: P.getAll, delete: P.delete, getAllKeys: P.getAllKeys };
  const o = window.__orig;
  if (kind === 'constraint') P.put = function (v, k) { return this.add(v, k); };
  if (kind === 'abort-at-commit') P.getAllKeys = function (...a) {
    const r = o.getAllKeys.apply(this, a), tx = this.transaction;
    r.addEventListener('success', () => { try { tx.abort(); } catch (_) {} });
    return r; };
  if (kind === 'abort-after') P.put = function (...a) {
    const r = o.put.apply(this, a), tx = this.transaction;
    r.addEventListener('success', () => { try { tx.abort(); } catch (_) {} });
    return r; };
  if (kind === 'abort-pending') P.put = function (...a) {
    const r = o.put.apply(this, a);
    try { this.transaction.abort(); } catch (_) {}
    return r; };
  if (kind === 'read-fails') P.getAll = function () { throw new DOMException('Lesing feilet (test)', 'UnknownError'); };
  if (kind === 'get-fails') P.get = function () { throw new DOMException('Lesing feilet (test)', 'UnknownError'); };
  if (kind === 'second-delete-throws') { let n = 0; P.delete = function (...a) {
    if (++n === 2) throw new DOMException('Sletting feilet (test)', 'UnknownError');
    return o.delete.apply(this, a); }; }
}"""
UNSTUB = """() => { const P = IDBObjectStore.prototype, o = window.__orig;
  if (o) Object.assign(P, { put: o.put, get: o.get, getAll: o.getAll, delete: o.delete, getAllKeys: o.getAllKeys }); }"""

# How a backup write ends — or that it never does. A hang reads as 'hung', never as a pass; a missing
# function (the old API) reads as 'missing', never as a crash that hides the checks after it.
WRITE = """async ([which, ms]) => {
  const call = () => which === 'daily'
    ? BackupDB.saveDaily(Store.toJSON(), Store.data.sessions.length)
    : BackupDB.saveBefore('test');
  let p; try { p = call(); } catch (e) { return 'missing:' + e.name; }
  return Promise.race([
    Promise.resolve(p).then(v => 'resolved:' + v, e => 'rejected:' + ((e && e.name) || String(e))),
    new Promise(r => setTimeout(() => r('hung'), ms)) ]);
}"""

# Raw access: every record (key order), a delete, a put — never through BackupDB.
_RAW_OPEN = """const P = IDBObjectStore.prototype, o = window.__orig || {};
  const r = indexedDB.open('lpl_backups'); r.onerror = () => rej(r.error);"""
RAW = """async () => new Promise((res, rej) => { """ + _RAW_OPEN + """
  r.onsuccess = () => { const db = r.result, tx = db.transaction('backups'), st = tx.objectStore('backups');
    const q = (o.getAll || P.getAll).call(st), k = (o.getAllKeys || P.getAllKeys).call(st);
    tx.oncomplete = () => { db.close(); res(JSON.stringify(k.result.map((key, i) => [key, q.result[i]]))); };
    tx.onerror = () => { db.close(); rej(tx.error); }; };
})"""
RAW_DEL = """async (key) => new Promise((res, rej) => { """ + _RAW_OPEN + """
  r.onsuccess = () => { const db = r.result, tx = db.transaction('backups', 'readwrite');
    (o.delete || P.delete).call(tx.objectStore('backups'), key);
    tx.oncomplete = () => { db.close(); res(); }; tx.onerror = () => { db.close(); rej(tx.error); }; };
})"""
RAW_PUT = """async ([key, rec]) => new Promise((res, rej) => { """ + _RAW_OPEN + """
  r.onsuccess = () => { const db = r.result, tx = db.transaction('backups', 'readwrite');
    (o.put || P.put).call(tx.objectStore('backups'), rec, key);
    tx.oncomplete = () => { db.close(); res(); }; tx.onerror = () => { db.close(); rej(tx.error); }; };
})"""

CARD = "() => (document.getElementById('backupList') || {}).textContent || ''"
TODAY = "() => localISODate()"
VISIBILITY = """(state) => { Object.defineProperty(document, 'visibilityState', { value: state, configurable: true });
  document.dispatchEvent(new Event('visibilitychange')); }"""


def records(page):
    return {k: v for k, v in json.loads(page.evaluate(RAW))}


def day_keys(page):
    return sorted(k for k in records(page) if len(k) == 10 and k[4] == "-" and k[7] == "-")


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
    # Chromium alone takes the File System Access path in FileIO.save(), which needs a user gesture and
    # a file handle — a headless run has neither, so the save "fails" and the link-apply (rightly)
    # never starts its analysis. Every engine takes the cache path here, as WebKit and Firefox always do.
    pg.evaluate("() => { FileIO.supportsApi = false; }")
    today = pg.evaluate(TODAY)

    print("== control: the startup load wrote today's DAILY copy ==")
    check("control: one record, today's, a daily copy of the 4 sessions",
          [(k, v.get("kind"), v.get("sessionCount")) for k, v in records(pg).items()], [(today, "day", 4)])
    check("control: no backup failure recorded yet", pg.evaluate("() => !BackupDB.lastError"), True)

    print("== a failed write is a failure: it rejects, it never hangs, it never looks saved ==")
    pg.evaluate(RAW_DEL, today)
    pg.evaluate(STUB, "abort-at-commit")
    check("aborted at commit, after every request succeeded (a quota failure) → rejects, does not hang",
          pg.evaluate(WRITE, ["daily", 2500]), "rejected:AbortError")
    pg.evaluate(UNSTUB)
    pg.evaluate(STUB, "abort-after")
    check("aborted after the write succeeded, with the trim still pending → rejects with AbortError",
          pg.evaluate(WRITE, ["daily", 2500]), "rejected:AbortError")
    pg.evaluate(UNSTUB)
    pg.evaluate(STUB, "abort-pending")
    # Here the NEXT request of the same save (the trim's key read) meets the aborted transaction first,
    # so the reason is TransactionInactiveError — true, just not the abort's own name. What matters:
    # a named rejection, never success and never a hang.
    out = pg.evaluate(WRITE, ["daily", 2500])
    check("aborted with the write still pending → rejects with a named error",
          (out.startswith("rejected:"), out not in ("rejected:null", "rejected:undefined")), (True, True))
    pg.evaluate(UNSTUB)
    check("control: none of those left a copy behind", today in records(pg), False)

    check("control: a working «før endring» write", pg.evaluate(WRITE, ["before", 2500]), "resolved:written")
    before = pg.evaluate(RAW)
    pg.evaluate(STUB, "constraint")
    check("a request error (ConstraintError) → rejects WITH THAT ERROR, not null, not success",
          pg.evaluate(WRITE, ["before", 2500]), "rejected:ConstraintError")
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
    pg.evaluate(f"async () => {{ await BackupDB.restore('{BEFORE}'); await Settings.renderBackupList(); }}")
    check("...nor does a restore read", "Siste sikkerhetskopi feilet" in pg.evaluate(CARD), True)
    check("control: today's copy can be written again", pg.evaluate(WRITE, ["daily", 2500]), "resolved:written")
    check("...a daily copy that finds today's already there stores nothing",
          pg.evaluate(WRITE, ["daily", 2500]), "resolved:exists")
    pg.evaluate(STUB, "constraint")
    pg.evaluate(WRITE, ["before", 2500])          # fail again, then skip again: the skip must not clear it
    pg.evaluate(UNSTUB)
    pg.evaluate(WRITE, ["daily", 2500])
    pg.evaluate("async () => { await Settings.renderBackupList(); }")
    check("...and that skip does not take the warning down", "Siste sikkerhetskopi feilet" in pg.evaluate(CARD), True)
    check("...the next successful write resolves", pg.evaluate(WRITE, ["before", 2500]), "resolved:written")
    pg.evaluate("async () => { await Settings.renderBackupList(); }")
    check("...and takes the warning down", "Siste sikkerhetskopi feilet" in pg.evaluate(CARD), False)
    # ...and the card follows a write ON ITS OWN, with no render call: Tøm alle sits on this very page,
    # so if its copy fails the warning must appear where he is looking. (Every check above renders
    # by hand, so a write that stopped redrawing the card passed them all — falsified 2026-10-02.)
    pg.evaluate(STUB, "constraint")
    pg.evaluate(WRITE, ["before", 2500])
    pg.evaluate(UNSTUB)
    pg.wait_for_timeout(300)
    check("a failed write puts the warning on the open card by itself", "Siste sikkerhetskopi feilet" in pg.evaluate(CARD), True)
    # Shown by hand first, so the next check cannot pass merely because the warning never came up.
    pg.evaluate("async () => { await Settings.renderBackupList(); }")
    pg.evaluate(WRITE, ["before", 2500])
    pg.wait_for_timeout(300)
    check("...and the next good write takes it down by itself", "Siste sikkerhetskopi feilet" in pg.evaluate(CARD), False)

    print("== a list that cannot be read is not an empty list ==")
    before = pg.evaluate(RAW)
    pg.evaluate(STUB, "read-fails")
    pg.evaluate("async () => { try { await Settings.renderBackupList(); } catch (_) {} }")
    card = pg.evaluate(CARD)
    pg.evaluate(UNSTUB)
    check("a failed read says «Kunne ikke lese sikkerhetskopiene»", "Kunne ikke lese sikkerhetskopiene" in card, True)
    check("...and never «Ingen sikkerhetskopier ennå»", "Ingen sikkerhetskopier ennå" in card, False)
    check("...and every stored record is byte-identical", pg.evaluate(RAW) == before, True)

    print("== the trim is all-or-nothing, and it keeps 7 DAILY copies + «før endring» ==")
    for d in range(1, 10):
        pg.evaluate(RAW_PUT, [f"2026-09-0{d}", {"kind": "day", "date": f"2026-09-0{d}", "timestamp": f"2026-09-0{d}T08:00:00.000Z",
                                                  "sessionCount": d, "json": "{}"}])
    pg.evaluate(RAW_DEL, today)
    before = pg.evaluate(RAW)
    check("control: 9 old daily copies + «før endring», today's missing",
          (len(day_keys(pg)), BEFORE in records(pg), today in records(pg)), (9, True, False))
    pg.evaluate(STUB, "second-delete-throws")
    check("a delete failing part-way through the trim → the save rejects", pg.evaluate(WRITE, ["daily", 2500]),
          "rejected:UnknownError")
    pg.evaluate(UNSTUB)
    check("...and nothing is written or deleted", pg.evaluate(RAW) == before, True)
    check("control: without the stub today's copy is written and the ring trimmed to the 7 newest days",
          (pg.evaluate(WRITE, ["daily", 2500]), day_keys(pg)[-1:], len(day_keys(pg))), ("resolved:written", [today], 7))
    check("...and «før endring» is never trimmed", BEFORE in records(pg), True)

    print("== the FIRST state seen today is today's copy ==")
    pg.evaluate(RAW_DEL, today)
    pg.evaluate("async () => { Store.load(Store.toJSON(), { snapshot: true }); await new Promise(r => setTimeout(r, 400)); }")
    first = records(pg).get(today, {})
    pg.evaluate("""async () => { const s = JSON.parse(JSON.stringify(Store.data.sessions[0])); s.id = 'e';
      Store.data.sessions.push(s); Store.load(Store.toJSON(), { snapshot: true }); await new Promise(r => setTimeout(r, 400)); }""")
    check("a load writes today's copy", (first.get("kind"), first.get("sessionCount")), ("day", 4))
    check("...and a later load the same day leaves it alone (still 4 sessions, not 5)",
          records(pg).get(today, {}).get("sessionCount"), 4)
    # An empty dataset has nothing to protect: it must not take the day's slot from the data that
    # follows (a fresh device opening before its Drive pull). One rule, inside saveDaily, for both the
    # load and the visibility path.
    pg.evaluate(RAW_DEL, today)
    empty = pg.evaluate("""async () => { const keep = Store.toJSON();
      Store.load(JSON.stringify({ sessions: [], shoes: [], goals: {}, events: [] }), { snapshot: true });
      await new Promise(r => setTimeout(r, 300));
      Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true });
      document.dispatchEvent(new Event('visibilitychange'));
      await new Promise(r => setTimeout(r, 300));
      const direct = await BackupDB.saveDaily('{"sessions":[]}', 0);
      Store.load(keep, { snapshot: false }); return direct; }""")
    check("an empty dataset never takes today's copy (load, visibility or a direct call)",
          (empty, today in records(pg)), ("empty", False))

    print("== first copy wins, atomically: two saves started together ==")
    pg.evaluate(RAW_DEL, today)
    race = pg.evaluate("""async () => {
      try {
        const a = BackupDB.saveDaily('{"sessions":[1,2,3]}', 3), b = BackupDB.saveDaily('{"sessions":[1]}', 1);
        return await Promise.all([a, b]);
      } catch (e) { return ['missing:' + e.name]; } }""")
    stored = records(pg).get(today, {}).get("sessionCount")
    check("exactly one of them writes, the other finds the copy", sorted(race), ["exists", "written"])
    check("...and the stored copy is the payload of the call that wrote",
          stored, {"written": 3}.get(race[0], 1) if len(race) == 2 else "missing")

    print("== a tab becoming VISIBLE takes today's copy; becoming hidden does nothing ==")
    pg.evaluate(RAW_DEL, today)
    pg.evaluate(VISIBILITY, "hidden"); pg.wait_for_timeout(400)
    check("hidden → nothing is written", today in records(pg), False)
    pg.evaluate(VISIBILITY, "visible"); pg.wait_for_timeout(400)
    check("visible → today's copy, of the state the tab holds (5 sessions)",
          records(pg).get(today, {}).get("sessionCount"), 5)
    pg.evaluate("() => { Store.data.sessions.pop(); }")
    pg.evaluate(VISIBILITY, "hidden"); pg.evaluate(VISIBILITY, "visible"); pg.wait_for_timeout(400)
    check("...and later returns the same day leave it alone (still 5)", records(pg).get(today, {}).get("sessionCount"), 5)
    # Every return to the tab runs this; with today's copy there, nothing changed, so the card is not
    # redrawn — a redraw reads all 8 copies back (a few MB on the phone) for nothing.
    reads = pg.evaluate("""async () => { let n = 0; const orig = BackupDB.getAll;
      BackupDB.getAll = function () { n++; return orig.apply(this, arguments); };
      Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true });
      document.dispatchEvent(new Event('visibilitychange'));
      await new Promise(r => setTimeout(r, 400)); BackupDB.getAll = orig; return n; }""")
    check("...without reading the copies back to redraw a card that has nothing new", reads, 0)
    pg.evaluate("() => { delete document.visibilityState; }")

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
    LINK_SETUP = """() => { StravaBackfill.proposed = [{ sessionId: 'd', activityId: 999 }];
      document.getElementById('backfillBody').innerHTML = '<input type="checkbox" checked data-i="0">'; }"""
    pg.evaluate(LINK_SETUP)
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

    print("== linking and the analysis it starts are ONE change: «før endring» keeps the pre-link state ==")
    pg.evaluate(LINK_SETUP)
    pg.evaluate("async () => { window.__analyzed = 0; await StravaBackfill.apply(); await new Promise(r => setTimeout(r, 800)); }")
    rec = records(pg).get(BEFORE, {})
    pre = json.loads(rec.get("json") or "{}")
    check("control: the link happened and started the analysis",
          (pg.evaluate("() => (Store.data.sessions.find(s => s.id === 'd') || {}).stravaId"),
           pg.evaluate("() => window.__analyzed") > 0), ("999", True))
    check("«før endring» names the link", rec.get("reason"), LINK)
    check("...and holds the state BEFORE it (d not yet linked)",
          next((s.get("stravaId") for s in pre.get("sessions", []) if s.get("id") == "d"), "missing"), None)

    print("== ordinary saves and loads are never blocked by a failing backup ==")
    pg.evaluate(RAW_DEL, today)
    pg.evaluate(STUB, "get-fails")
    load = pg.evaluate("""async () => { const ok = Store.load(Store.toJSON(), { snapshot: true });
      await new Promise(r => setTimeout(r, 400)); return { ok, n: Store.data.sessions.length }; }""")
    # Judged on the local cache, the one store every engine writes: FileIO.save()'s own return value
    # depends on the engine (Chromium takes the file-picker path, which fails headless).
    cached = pg.evaluate("""async () => { Store.data.sessions[0].oktnavn = 'Markør'; await FileIO.save();
      return JSON.parse(localStorage.getItem('lpl_cache')).sessions[0].oktnavn; }""")
    pg.evaluate(UNSTUB)
    check("a load whose daily copy fails still loads", load, {"ok": True, "n": 4})
    check("control: ...and that daily copy really did fail", today in records(pg), False)
    check("an ordinary save with a failing backup still writes the data", cached, "Markør")

    print("== «Tøm alle data» ==")
    pg.evaluate(WRITE, ["daily", 2500])
    pg.evaluate("() => switchTab('settings')")
    pg.wait_for_timeout(300)
    n_before = pg.evaluate("() => Store.data.sessions.length")
    daily_before = records(pg).get(today)
    pg.evaluate(STUB, "constraint")
    dialogs.clear()
    pg.click("#btnClearAll")
    pg.wait_for_timeout(800)
    pg.evaluate(UNSTUB)
    check("with a failing copy, every session is still there", pg.evaluate("() => Store.data.sessions.length"), n_before)
    check("...and it says so (an alert: nothing was deleted)", any("ingenting er slettet" in m for m in dialogs), True)
    check("its confirm no longer claims it can't be undone, and says where the copy is",
          [("kan ikke angres" in m, "Lokale sikkerhetskopier" in m) for m in dialogs[:1]], [(False, True)])
    dialogs.clear()
    pg.click("#btnClearAll")
    pg.wait_for_timeout(800)
    rec = records(pg).get(BEFORE, {})
    check("with a working copy it clears", pg.evaluate("() => Store.data.sessions.length"), 0)
    check("...«før endring» now names «Tøm alle data» (the second change overwrote the link's copy)",
          rec.get("reason"), CLEAR)
    check("...and holds every session from before the clear", rec.get("sessionCount"), n_before)
    check("...and today's daily copy is untouched", records(pg).get(today) == daily_before, True)

    print("== the card, and restoring from it ==")
    pg.evaluate("async () => { await Settings.renderBackupList(); }")
    rows = pg.evaluate("() => [...document.querySelectorAll('#backupList button')].map(b => b.parentElement.textContent.trim())")
    check("«Før «Tøm alle data»» is listed first", bool(rows) and rows[0].startswith(f"Før «{CLEAR}»"), True)
    dialogs.clear()
    pg.evaluate(f"async () => {{ await Settings.restoreBackup('{BEFORE}'); }}")
    pg.wait_for_timeout(500)
    check("restoring «før endring» brings the sessions back", pg.evaluate("() => Store.data.sessions.length"), n_before)
    check("...its confirm names what it restores", any(f"før «{CLEAR}»" in m for m in dialogs), True)
    pg.goto(APP); pg.wait_for_timeout(700)
    check("...and it survives a reload", pg.evaluate("() => Store.data.sessions.length"), n_before)
    old_json = json.dumps({"sessions": [{"id": "x1", "dato": "2026-09-15", "løpetype": "utendors", "distanse": 5, "varighet": 1800},
                                        {"id": "x2", "dato": "2026-09-16", "løpetype": "utendors", "distanse": 6, "varighet": 2100}],
                           "shoes": [], "goals": {}, "events": []})
    pg.evaluate(RAW_PUT, ["2026-09-15", {"date": "2026-09-15", "timestamp": "2026-09-15T07:00:00.000Z", "sessionCount": 2, "json": old_json}])
    pg.evaluate("() => switchTab('settings')")
    pg.evaluate("async () => { await Settings.renderBackupList(); }")
    check("a copy written before this change (no kind) still lists as a daily copy", "15.09.2026" in pg.evaluate(CARD), True)
    pg.evaluate("async () => { await Settings.restoreBackup('2026-09-15'); }")
    pg.wait_for_timeout(500)
    check("...and restores", pg.evaluate("() => Store.data.sessions.map(s => s.id)"), ["x1", "x2"])
    check("no page errors", errs, [])
    pg.close()

    print("== the day is the LOCAL calendar day (Europe/Oslo, a fixed clock) ==")
    ctx = b.new_context(timezone_id="Europe/Oslo")
    p2 = ctx.new_page()
    errs2 = []
    p2.on("pageerror", lambda e: errs2.append(str(e)))
    p2.clock.set_fixed_time("2026-09-28T22:30:00Z")          # 00:30 on the 29th in Oslo, 22:30 on the 28th in UTC
    p2.goto(APP); p2.evaluate(SEED); p2.goto(APP)
    p2.wait_for_timeout(800)
    check("a load at 00:30 local files under the LOCAL date (29th), not UTC's 28th", day_keys(p2), ["2026-09-29"])
    p2.evaluate(RAW_DEL, "2026-09-29")
    p2.clock.set_fixed_time("2026-09-28T21:59:00Z")          # 23:59 on the 28th
    a1 = p2.evaluate(WRITE, ["daily", 2500])
    p2.clock.set_fixed_time("2026-09-28T22:01:00Z")          # 00:01 on the 29th
    a2 = p2.evaluate(WRITE, ["daily", 2500])
    check("23:59 and 00:01 are two different days", (a1, a2, day_keys(p2)),
          ("resolved:written", "resolved:written", ["2026-09-28", "2026-09-29"]))
    p2.evaluate(WRITE, ["before", 2500])
    for d in range(1, 10):
        p2.clock.set_fixed_time(f"2026-10-0{d}T10:00:00Z")
        p2.evaluate(WRITE, ["daily", 2500])
    check("nine more days later: the 7 newest daily copies", day_keys(p2), [f"2026-10-0{d}" for d in range(3, 10)])
    check("...and «før endring» beside them", BEFORE in records(p2), True)
    check("no page errors (Oslo context)", errs2, [])
    ctx.close()
    b.close()

print(f"\n{passed}/{passed + failed} passed" + (f"  ({failed} FAILED)" if failed else ""))
sys.exit(1 if failed else 0)
