"""Content-Security-Policy — where the page may load scripts from and send data to.  (2026-09-28)

Standalone — NOT part of run_all.py, which is the fast no-browser gate. Run directly:
    python tests/test_csp.py                    (WebKit, as CI runs it)
    PW_ENGINE=firefox python tests/test_csp.py  (also chromium; firefox is his main browser)

Ported from the template's 2026-09-25 audit, adapted to Puls. Puls needs 'unsafe-inline' (its main
script and the on…= handlers are inline), so the policy cannot stop an injected inline script. What
it limits is WHERE the page can send data — connect-src: Google Drive and sign-in, Strava, GitHub and
his own worker, nothing else — and where scripts can come from. His Drive and Strava tokens live in
localStorage.

The worker is named EXACTLY (his call, 2026-09-28): a Worker URL other than his own is blocked until
the policy names it too, so only the known worker can receive a token. A fork adds its own host.

The risk is a missed origin: Drive or Strava breaking on the live site with nothing visibly wrong.
So, on an https origin (how Pages serves it — the only place the version footer asks GitHub) and on
file:// (how the suites and a local copy run):
  * a tour of every tab, a run's detail view, Løpeatlas's flags (data: images) and both downloads
    records ZERO violations — next to controls that each of those really rendered or happened;
  * every allowed origin is fetched through a stub: the request must go OUT, with no violation;
  * a positive control proves a violation is observable at all: a fetch to a host the policy does not
    name must fail with a connect-src violation for THAT host — another *.workers.dev host included,
    so widening the worker to a wildcard turns this red;
  * statically: the policy comes before any script or link, every https:// host in puls.html is in
    the policy or in NOT_LOADED with its reason, and every fetch() target is in connect-src — a new
    endpoint fails here instead of on the live site.
WebKit does not apply connect-src to a fetch from a file:// page (it does apply script-src there), so
on WebKit the file:// control prints SKIP — never a PASS it did not earn. connect-src is proven over
https on every engine.
Synthetic data only. Every external request is answered by a stub except Chart.js, which comes from
the CDN exactly as the page asks for it (SRI and all).
"""
import os, pathlib, re, sys
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

ENGINE = os.environ.get("PW_ENGINE", "webkit")
ROOT = pathlib.Path(__file__).resolve().parent.parent
HTML = (ROOT / "puls.html").read_text(encoding="utf-8")
FILE_URL = (ROOT / "puls.html").as_uri()
HTTPS_URL = "https://puls.test/running/puls.html"          # stands in for psvadev.github.io
WORKER = "https://puls-strava-auth.petter-cerb.workers.dev"
ALLOWED = ["https://www.googleapis.com", "https://oauth2.googleapis.com", "https://www.strava.com",
           "https://api.github.com", WORKER]
EXPECTED = {
    "default-src": ["'self'"],
    "script-src": ["'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net"],
    "style-src": ["'self'", "'unsafe-inline'"],
    "img-src": ["'self'", "data:"],
    "connect-src": ["'self'"] + ALLOWED,
    "object-src": ["'none'"],
    "base-uri": ["'none'"],
    "form-action": ["'self'"],
}
# Hosts puls.html names but the PAGE never loads from — each with its reason, so a new one is argued.
NOT_LOADED = {
    "https://accounts.google.com": "Google sign-in is a page navigation (window.location), not a fetch",
    "https://github.com": "links: the repo, and the deployed commit in the version footer",
    "https://flagcdn.com": "named in a comment only — flags are inline data: images since 2026-08-27",
    "https://xxx.workers.dev": "the Worker URL field's placeholder text",
}
BLOCKED = ["https://example.com", "https://someone-else.workers.dev"]
TABS = ["form", "dash", "log", "atlas", "plan", "tools", "settings"]
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


def line_of(pos):
    return HTML.count("\n", 0, pos) + 1


# ── static ────────────────────────────────────────────────────────────────────────────────────────
print("== static ==")
meta = re.search(r'<meta http-equiv="Content-Security-Policy"\s+content="([^"]+)"', HTML)
check("puls.html declares a Content-Security-Policy", bool(meta), True)
policy = {}
for part in (meta.group(1) if meta else "").split(";"):
    if part.split():
        policy[part.split()[0]] = part.split()[1:]
check("the policy is exactly the reviewed one", policy, EXPECTED)
firsts = [i for i in (HTML.find("<script"), HTML.find("<link")) if i >= 0]
check("the policy comes before every script and link", bool(meta) and meta.start() < min(firsts), True)

HOST = r"https://[A-Za-z0-9.-]*[A-Za-z0-9]"
loaded = {s for d in ("connect-src", "script-src", "img-src") for s in policy.get(d, []) if s.startswith("https://")}
unclassified = {}
for hm in re.finditer(HOST, HTML):
    if hm.group() not in loaded and hm.group() not in NOT_LOADED:
        unclassified.setdefault(hm.group(), line_of(hm.start()))
check("every https:// host in puls.html is in the policy or NOT_LOADED", unclassified, {})
check("every NOT_LOADED host is still named in puls.html", [h for h in NOT_LOADED if h not in HTML], [])

connect = policy.get("connect-src", [])
bad_fetch = {}
for fm in re.finditer(r"(?<![\w.$])fetch\((?!\))", HTML):     # `fetch()` with nothing inside is prose
    arg = HTML[fm.end():fm.end() + 80].lstrip()
    lit = re.match(r"[`'\"](" + HOST + ")", arg)
    if lit:
        target = lit.group(1)
    elif arg.startswith("`${_workerUrl()}"):
        target = WORKER
    elif re.match(r"url\s*,", arg):
        continue                     # _authedFetch's own call — its callers are checked below
    else:
        target = arg[:40]
    if target not in connect:
        bad_fetch[line_of(fm.start())] = target
for am in re.finditer(r"_authedFetch\(\s*[`'\"](" + HOST + ")", HTML):
    if am.group(1) not in connect:
        bad_fetch[line_of(am.start())] = am.group(1)
check("every fetch() target is in connect-src", bad_fetch, {})
check("only _authedFetch hands fetch() a variable",
      len(re.findall(r"(?<![\w.$])fetch\(\s*url\s*,", HTML)), 1)
check("no other way to send data (XHR, beacon, socket, event stream)",
      re.findall(r"XMLHttpRequest|sendBeacon|new WebSocket|new EventSource", HTML), [])

# ── in the browser ────────────────────────────────────────────────────────────────────────────────
# Recorded from the first line of every document; a capture listener, so nothing stops it bubbling.
REC = """
window.__csp = [];
document.addEventListener('securitypolicyviolation', e => window.__csp.push(
  (e.effectiveDirective || e.violatedDirective) + ' ' + (e.blockedURI || '(inline)')), true);
"""
# Four runs in four countries: NO/SE/JP have bundled SVG flags, DE takes the emoji fallback (a canvas
# drawing turned into a PNG) — both are data: images. isoWeek is the app's own; it is guarded because a
# policy that blocks the app's script must reach the boot check below, not crash the seed.
SEED = """() => {
  const week = d => typeof isoWeek === 'function' ? isoWeek(d) : null;
  const run = (id, dato, land) => ({ id, dato, uke: week(dato), oktnavn: 'Tur', okttype: 'Easy',
    treningsplan: 'Runna', løpetype: 'utendors', distanse: 8, varighet: 2880, tempo: 360,
    soner: [0, 600, 1200, 0, 0], land });
  localStorage.setItem('lpl_cache', JSON.stringify({
    sessions: [run('a', '2026-09-20', 'NO'), run('b', '2026-09-22', 'SE'), run('c', '2026-09-24', 'JP'),
               run('d', '2026-09-26', 'DE')],
    shoes: [], shoeDefaults: {}, goals: {}, events: [], plannedSessions: [],
    settings: { zones: [] }, lastUpdated: '' }));
}"""
PROBE = "async url => { try { return (await fetch(url)).status; } catch (e) { return e.name; } }"
FOOTER = '[{"sha": "0123456789abcdef0123", "commit": {"committer": {"date": "2026-09-28T12:00:00Z"}}}]'
sent = []                            # every request a stub answered: proof it LEFT the page


def stub(route):
    url = route.request.url
    sent.append(url)
    route.fulfill(status=200, body=FOOTER if url.startswith("https://api.github.com/") else "{}",
                  headers={"content-type": "application/json", "access-control-allow-origin": "*"})


def open_page(ctx, url, label):
    """The page, what it logged, and whether the app came up at all. A policy that blocks the app's
    own script must fail HERE, by name, with the violations — not as a timeout traceback."""
    pg = ctx.new_page()
    obs = {"errors": [], "console": []}
    pg.on("pageerror", lambda e: obs["errors"].append(str(e)))
    pg.on("console", lambda m: obs["console"].append(m.text)
          if re.search(r"Content[- ]Security[- ]Policy", m.text, re.I) else None)
    pg.goto(url)
    pg.evaluate(SEED)
    pg.reload()
    try:
        pg.wait_for_function("() => typeof Chart !== 'undefined' && typeof Store !== 'undefined'"
                             " && Store.data.sessions.length === 4", timeout=30000)
        booted = True
    except Exception:
        booted = False
    check(f"{label}: the app boots under the policy", booted or pg.evaluate("() => window.__csp.slice()"), True)
    pg.wait_for_timeout(300)
    return pg, obs, booted


def tour(pg, obs):
    for t in TABS:
        pg.evaluate("t => switchTab(t)", t)
        pg.wait_for_timeout(150)
    obs["last tab"] = pg.evaluate("() => document.querySelector('.panel.active')?.id")
    pg.evaluate("() => switchTab('atlas')")
    pg.wait_for_timeout(300)
    obs["flags drawn"] = pg.evaluate("""() => [...document.querySelectorAll('#panel-atlas img')]
        .filter(i => i.src.startsWith('data:image/') && i.complete && i.naturalWidth > 0).length > 0""")
    pg.evaluate("() => DetailPanel.openSession('a')")
    pg.wait_for_timeout(300)
    obs["detail open"] = pg.evaluate("""() => document.getElementById('detailModal').classList.contains('open')
        && document.getElementById('detailBody').innerText.trim().length > 0""")
    pg.evaluate("() => DetailPanel.close()")
    pg.evaluate("() => switchTab('log')")
    with pg.expect_download(timeout=10000) as d:
        pg.click("#btnDownloadTsv")
    obs["TSV"] = d.value.suggested_filename
    pg.evaluate("() => switchTab('settings')")
    with pg.expect_download(timeout=10000) as d:
        pg.click("#btnDownload")
    obs["JSON"] = d.value.suggested_filename
    obs["footer"] = pg.inner_text("#appVersionFooter")
    pg.wait_for_timeout(200)
    obs["violations"] = pg.evaluate("() => window.__csp.slice()")
    obs["console at tour end"] = list(obs["console"])


def control(pg):
    """A host the policy does not name: (the fetch failed, nothing left the page, a connect-src
    violation named that host) — per host."""
    pg.evaluate("() => { window.__csp.length = 0; }")
    res = {}
    for o in BLOCKED:
        url = o + "/csp-probe"
        status = pg.evaluate(PROBE, url)
        pg.wait_for_timeout(300)
        seen = pg.evaluate("() => window.__csp.slice()")
        res[o] = (status != 200, url in sent, any(v.startswith("connect-src " + o) for v in seen))
    return res


CONTROL_OK = {o: (True, False, True) for o in BLOCKED}


def report_tour(label, obs, https):
    check(f"{label}: the tour records no violation", obs["violations"], [])
    check(f"{label}: no CSP message in the console", obs["console at tour end"], [])
    check(f"{label}: no page errors", obs["errors"], [])
    check(f"{label}: the tour did what it claims (every tab, flags, detail view, both downloads)",
          (obs["last tab"], obs["flags drawn"], obs["detail open"], obs["TSV"], obs["JSON"]),
          ("panel-settings", True, True, "løpelogg.tsv", "puls.json"))
    if https:
        check(f"{label}: the version footer got its answer from GitHub", "v0123456" in obs["footer"], True)


with sync_playwright() as p:
    b = getattr(p, ENGINE).launch()
    ctx = b.new_context(viewport={"width": 1280, "height": 900}, accept_downloads=True)
    ctx.add_init_script(REC)
    ctx.route(re.compile(r"^https://(" + "|".join(re.escape(u[8:]) for u in ALLOWED + BLOCKED) + r")/"), stub)
    ctx.route("https://puls.test/**", lambda r: r.fulfill(
        status=200, body=HTML, headers={"content-type": "text/html; charset=utf-8"}))

    print(f"== https origin ({ENGINE}) ==")
    https_control = None
    pg, obs, booted = open_page(ctx, HTTPS_URL, "https")
    if booted:
        tour(pg, obs)
        report_tour("https", obs, True)
        pg.evaluate("() => { window.__csp.length = 0; }")      # the next check is about THESE fetches
        got = {}
        for o in ALLOWED:
            status = pg.evaluate(PROBE, o + "/csp-probe")
            got[o] = (status, o + "/csp-probe" in sent)
        pg.wait_for_timeout(300)
        check("https: every allowed origin is reachable — the request went out and was answered",
              got, {o: (200, True) for o in ALLOWED})
        check("https: ...with no violation", pg.evaluate("() => window.__csp.slice()"), [])
        https_control = control(pg)
        check("https: a host the policy does not name is blocked, with a connect-src violation for it",
              https_control, CONTROL_OK)
    pg.close()

    print(f"== file:// ({ENGINE}) ==")
    pg, obs, booted = open_page(ctx, FILE_URL, "file://")
    if booted:
        tour(pg, obs)
        report_tour("file://", obs, False)
        file_control = control(pg)
        if file_control != CONTROL_OK and https_control == CONTROL_OK:
            # The policy works (the https control proved it), but this engine does not apply
            # connect-src to a fetch from a file:// page — WebKit, 2026-09-28. It DOES apply script-src
            # there (a policy without 'unsafe-inline' stops the app booting on file:// too), so the tour
            # above still means something; only this control would be a silence for the wrong reason.
            # connect-src is proven over https, on every engine, above.
            skip("file://: connect-src control", f"{ENGINE} does not apply connect-src on file://: {file_control}")
        else:
            check("file://: a host the policy does not name is blocked, with a connect-src violation for it",
                  file_control, CONTROL_OK)
    pg.close()
    ctx.close()
    b.close()

print(f"\n{passed}/{passed + failed} passed" + (f"  ({failed} FAILED)" if failed else ""))
sys.exit(1 if failed else 0)
