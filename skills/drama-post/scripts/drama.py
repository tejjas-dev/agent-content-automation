#!/usr/bin/env python3
"""Helper for the drama pipeline: paths, queue, tasks, domains, log. Stdlib only.

  drama.py env                       SK / PY / DATA / ROOT as key=value (also migrates old data once).
                                     SK is the draft-aware view while READY drafts exist (then DRAFTS= / NOTES= are printed too)
  drama.py task "<title>" [--fresh]  create ROOT/work/<utc>-<slug>, print its path; an unfinished task of the same title is reused (crash resume)
  drama.py step TASK                 STEP FIND | SCRAPE | SHORT | PUBLISH | DONE  (first stage whose output is missing)
  drama.py enqueue "A" "B" ...       add titles (max 5 per call), print RUNNER or QUEUED position=N
                                     (no titles = resume a stuck queue)
  drama.py next                      RUNNER only: print the next title, or EMPTY (and give up the runner role)
  drama.py status | reset [--queue]
  drama.py notify "text"             private Telegram message to DEVX_NOTIFY_CHAT_ID (best effort, optional)
  drama.py domain get|set <primary|fallback|finder> [url]      (old names katdrama=primary, katworld=finder still work)
  drama.py domain refresh            primary dead/moved -> follow the finder redirect, verify, save (DOMAIN_UPDATED / DOMAIN_OK / DOMAIN_REFRESH_FAILED)
  drama.py log <stage> <code> [detail]   append one line to state/logs/events.jsonl (secrets are redacted)

Layout: DATA = $DEVX_DATA_DIR, else /workspace if writable, else ~/.devx-content
  DATA/drama/work/    per-drama task folders (everything temporary; cleaned by content-cleanup after 24 h)
  DATA/drama/state/   kept: queue.jsonl, runner.json, posted.jsonl, domains.json, learned/<source>.md, logs/, draft/
"""
import argparse
import ipaddress
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from pathlib import Path

try:
    import fcntl
except ImportError:
    fcntl = None

sys.path.insert(0, str(Path(__file__).absolute().parent))

SKILLS = Path(__file__).absolute().parents[2]
LEGACY = Path.home() / ".devx-content"
# primary = site used first (results load by JavaScript), fallback = behind Cloudflare, finder = redirects to the live primary domain
DEFAULT_DOMAINS = {"primary": "https://new.katdrama.my/", "fallback": "https://katdrama.org/",
                   "finder": "https://katworld.net/?type=KatDrama"}
ALIASES = {"katdrama": "primary", "katworld": "finder"}          # names used by 0.3.x
MAX_BATCH = 5
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def data_dir():
    e = os.environ.get("DEVX_DATA_DIR")
    if e:
        return Path(e)
    w = Path("/workspace")
    return w if w.is_dir() and os.access(w, os.W_OK) else LEGACY


def sub(name):
    p = data_dir() / "drama" / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def clean(s):
    return re.sub(r"\s+", " ", str(s)).strip()


def norm(s):
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def atomic_write(p, text):
    """Write via a temp file + rename so a crash never leaves a half-written state file."""
    t = p.with_name(p.name + ".tmp")
    t.write_text(text, encoding="utf-8")
    os.replace(t, p)


def redact(s):
    s = str(s)
    for k in ("TELEGRAM_BOT_TOKEN", "AROLINKS_TOKEN"):
        v = os.environ.get(k, "").strip()
        if len(v) >= 4:
            s = s.replace(v, "***")
    return s


def log_event(stage, code, detail="", **kw):
    """Best-effort structured log line; never raises, never contains secrets."""
    try:
        d = sub("state") / "logs"
        d.mkdir(parents=True, exist_ok=True)
        p = d / "events.jsonl"
        if p.exists() and p.stat().st_size > 512_000:
            os.replace(p, d / "events.jsonl.1")
        rec = {"ts": int(time.time()), "stage": stage, "code": code, "detail": redact(detail)[:200], **kw}
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        pass


def scrapling_python():
    for c in (data_dir() / "venv" / "bin" / "python", LEGACY / "venv" / "bin" / "python"):
        if c.exists():
            return str(c)
    return sys.executable


def migrate():
    st = sub("state")
    if (st / ".migrated").exists() or not LEGACY.exists() or LEGACY.resolve() == data_dir().resolve():
        return
    (st / "learned").mkdir(exist_ok=True)
    for f in (LEGACY / "learned").glob("*.md"):
        if not (st / "learned" / f.name).exists():
            shutil.copy(f, st / "learned" / f.name)
    if (LEGACY / "posted.jsonl").exists() and not (st / "posted.jsonl").exists():
        shutil.copy(LEGACY / "posted.jsonl", st / "posted.jsonl")
    (st / ".migrated").touch()


# ---- queue (all changes under one file lock) -------------------------------------------------
@contextmanager
def locked():
    f = open(sub("state") / "queue.lock", "a+")
    if fcntl:
        fcntl.flock(f, fcntl.LOCK_EX)
    try:
        yield
    finally:
        if fcntl:
            fcntl.flock(f, fcntl.LOCK_UN)
        f.close()


def read_q():
    """Tolerant: one damaged line never empties the queue; the original is kept as queue.jsonl.bad."""
    p = sub("state") / "queue.jsonl"
    try:
        raw = p.read_text(encoding="utf-8")
    except OSError:
        return []
    items, bad = [], 0
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            it = json.loads(line)
            if not (isinstance(it, dict) and clean(it.get("title", ""))):
                raise ValueError
            items.append(it)
        except ValueError:
            bad += 1
    if bad:
        try:
            shutil.copy(p, p.with_name("queue.jsonl.bad"))
        except OSError:
            pass
        print(f"QUEUE_REPAIRED dropped {bad} damaged line(s); original kept as queue.jsonl.bad", file=sys.stderr)
        log_event("queue", "QUEUE_REPAIRED", f"dropped={bad}")
    return items


def write_q(items):
    atomic_write(sub("state") / "queue.jsonl", "".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items))


def get_runner():
    try:
        r = json.loads((sub("state") / "runner.json").read_text(encoding="utf-8"))
        return r if isinstance(r, dict) else {}
    except (OSError, ValueError):
        return {}


def set_runner(d):
    p = sub("state") / "runner.json"
    if d is None:
        p.unlink(missing_ok=True)
    else:
        atomic_write(p, json.dumps(d))


def alive(r):
    return bool(r) and time.time() - r.get("ts", 0) < float(os.environ.get("DEVX_RUNNER_STALE", "2400"))


def cmd_enqueue(a):
    titles = list(dict.fromkeys(clean(t) for t in a.titles if clean(t)))
    with locked():
        q, r = read_q(), get_runner()
        active = alive(r)
        seen = {norm(i["title"]) for i in q} | ({norm(r["current"])} if active and r.get("current") else set())
        added, dups = [], []
        for t in titles[:MAX_BATCH]:
            (dups if norm(t) in seen else added).append(t)
            seen.add(norm(t))
        for t in titles[MAX_BATCH:]:
            print(f"SKIPPED_LIMIT {t}")
        if r and not active and r.get("current"):            # previous runner died mid-drama
            if r.get("retried"):
                print(f"DROPPED_STALE {r['current']}")
                log_event("queue", "DROPPED_STALE", r["current"])
            else:
                q.insert(0, {"title": r["current"], "retried": True})
        ahead = len(q) + (1 if active and r.get("current") else 0)
        q += [{"title": t, "ts": int(time.time())} for t in added]
        write_q(q)
        for t in dups:
            print(f"DUPLICATE {t}")                           # same title already waiting / running in THIS queue
        if active:
            print(f"QUEUED position={ahead + 1} added={len(added)}")
        elif q:
            set_runner({"ts": time.time(), "current": ""})
            print(f"RUNNER queued={len(q)}")
        else:
            set_runner(None)
            print("EMPTY")


def cmd_next(a):
    with locked():
        q = read_q()
        if not q:
            set_runner(None)
            print("EMPTY")
            return
        item = q.pop(0)
        write_q(q)
        set_runner({"ts": time.time(), "current": item["title"], "retried": bool(item.get("retried"))})
        print(item["title"])


def drafts_line():
    try:
        import proposal
        return proposal.summary()
    except Exception:  # noqa: BLE001
        return ""


def cmd_status(a):
    r = get_runner()
    print(f"runner={'active' if alive(r) else 'idle'} current={r.get('current', '')!r} queued={len(read_q())}")
    d = drafts_line()
    if d:
        print(f"drafts: {d}")
    try:
        lines = (sub("state") / "logs" / "events.jsonl").read_text(encoding="utf-8").splitlines()[-40:]
        bad = [json.loads(x) for x in lines if x.strip()]
        bad = [e for e in bad if e.get("code") not in ("OK", "INFO")][-3:]
        for e in bad:
            print(f"recent: {e.get('stage')}/{e.get('code')} {e.get('detail', '')[:80]}")
    except (OSError, ValueError):
        pass


def cmd_reset(a):
    with locked():
        set_runner(None)
        if a.queue:
            write_q([])
    print("reset ok" + (" (queue cleared)" if a.queue else ""))


# ---- paths / task / env ---------------------------------------------------------------------
def cmd_env(a):
    migrate()
    sub("work")
    sub("state")
    sk, extra = str(SKILLS), {}
    try:
        import proposal
        sk, extra = proposal.refresh(SKILLS)
    except Exception:  # noqa: BLE001  drafts are optional: never block a run
        pass
    print(f"SK={sk}\nPY={scrapling_python()}\nDATA={data_dir()}\nROOT={data_dir() / 'drama'}")
    for k, v in extra.items():
        print(f"{k}={v}")


def newest(p):
    try:
        return max([p.stat().st_mtime] + [c.stat().st_mtime for c in p.iterdir()])
    except OSError:
        return 0


def cmd_task(a):
    slug = re.sub(r"[^a-z0-9]+", "-", a.title.lower()).strip("-")[:40] or "x"
    work = sub("work")
    if not a.fresh:                                            # crash resume: same title, not finished, not failed on data
        window = float(os.environ.get("DEVX_TASK_REUSE", "21600"))
        for p in sorted(work.iterdir(), reverse=True):
            if (p.is_dir() and p.name[16:] == slug and not (p / ".done").exists() and not (p / ".failed").exists()
                    and time.time() - newest(p) < window):
                os.utime(p, None)
                print(p)
                return
    t = time.time()
    while (work / f"{time.strftime('%Y%m%d-%H%M%S', time.gmtime(t))}-{slug}").exists():
        t += 1                                                 # never share a folder (and its .done/.failed marks) with an older task
    p = work / f"{time.strftime('%Y%m%d-%H%M%S', time.gmtime(t))}-{slug}"
    p.mkdir(parents=True, exist_ok=True)
    print(p)


def cmd_step(a):
    t = Path(a.task)

    def jload(name):
        try:
            return json.loads((t / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    if (t / ".done").exists():
        stage = "DONE"
    elif not (t / "find.txt").is_file() or not (t / "find.txt").stat().st_size:
        stage = "FIND"
    else:
        data, links, short = jload("data.json"), jload("links.json"), jload("short.json")
        if not (isinstance(data, dict) and data.get("title") and data.get("poster") and isinstance(links, list) and links):
            stage = "SCRAPE"
        elif not (isinstance(short, list) and any(isinstance(s, dict) and s.get("short") for s in short)):
            stage = "SHORT"
        else:
            stage = "PUBLISH"
    print(f"STEP {stage}")


def cmd_log(a):
    log_event(a.stage, a.code, a.detail or "")
    print("logged")


# ---- domains --------------------------------------------------------------------------------
def domains():
    d = dict(DEFAULT_DOMAINS)
    try:
        for k, v in json.loads((sub("state") / "domains.json").read_text(encoding="utf-8")).items():
            k = ALIASES.get(k, k)
            if k in d and isinstance(v, str) and valid_site(v):
                d[k] = v
    except (OSError, ValueError, AttributeError):
        pass
    return d


def host_of(u):
    return re.sub(r"^www\.", "", (urllib.parse.urlsplit(u).hostname or "").lower())


def origin_of(u):
    s = urllib.parse.urlsplit(u)
    return f"{s.scheme}://{s.netloc}/"


def valid_site(u):
    """https URL of a real hostname (no IP literal, no credentials, standard port)."""
    try:
        s = urllib.parse.urlsplit(u)
        h = s.hostname or ""
        if s.scheme != "https" or "." not in h or s.username or s.password or s.port not in (None, 443):
            return False
        try:
            ipaddress.ip_address(h)
            return False
        except ValueError:
            return bool(re.fullmatch(r"[a-z0-9.-]+", h.lower()))
    except ValueError:
        return False


def probe(url, timeout=15):
    """-> (state, final_url, detail). ok = answers (a Cloudflare 403/503 still means alive); moved = redirected to
    another host; dead = DNS/connection/TLS error, 404/410 or 5xx."""
    code, final = 0, url
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=timeout) as r:
            code, final = r.status, r.geturl()
            r.read(2048)
    except urllib.error.HTTPError as e:
        code, final = e.code, e.geturl() or url
        if code in (404, 410) or (code >= 500 and code != 503):
            return "dead", final, f"HTTP {code}"
    except Exception as e:  # noqa: BLE001
        return "dead", url, type(e).__name__
    return ("moved" if host_of(final) != host_of(url) else "ok"), final, f"HTTP {code}"


def refresh_primary(d):
    cur = d["primary"]
    state, final, why = probe(cur)
    if state == "ok":
        print(f"DOMAIN_OK primary={cur}")
        return 0
    cand, how = None, ""
    if state == "moved":
        cand, how = origin_of(final), "primary redirects"
    else:
        fstate, ffinal, fwhy = probe(d["finder"])
        if fstate == "moved":
            cand, how = origin_of(ffinal), "finder redirect"
        else:
            how = f"finder gave {fstate} ({fwhy})"
    bad = None
    if not cand:
        bad = how
    elif not valid_site(cand):
        bad = f"candidate {cand} is not a plain https site"
    elif host_of(cand) in (host_of(cur), host_of(d["finder"])):
        bad = f"candidate {cand} is the old or the finder host"
    else:
        cstate, _, cwhy = probe(cand)
        if cstate != "ok":
            bad = f"candidate {cand} not reachable ({cwhy})"
    if bad:
        print(f"DOMAIN_REFRESH_FAILED primary={cur} reason={bad}")
        log_event("domain", "DOMAIN_REFRESH_FAILED", bad)
        return 1
    save_domain("primary", cand)
    print(f"DOMAIN_UPDATED primary {cur} -> {cand} ({how})")
    log_event("domain", "DOMAIN_UPDATED", f"{cur} -> {cand}")
    return 0


def save_domain(src, url):
    d = domains()
    custom = {k: v for k, v in d.items() if v != DEFAULT_DOMAINS.get(k)}
    custom[src] = url
    atomic_write(sub("state") / "domains.json", json.dumps(custom, indent=1))


def cmd_domain(a):
    d = domains()
    if a.op == "refresh":
        return refresh_primary(d)
    src = ALIASES.get(a.source, a.source)
    if src not in d:
        print(f"ERROR unknown source {a.source} (known: {', '.join(d)})")
        return 2
    if a.op == "get":
        print(d[src])
        return 0
    if not a.url or not valid_site(a.url):
        print("ERROR give an https:// URL of a real site")
        return 2
    save_domain(src, a.url)
    print(f"saved {src} = {a.url}")
    return 0


def cmd_notify(a):
    chat, tok = os.environ.get("DEVX_NOTIFY_CHAT_ID", "").strip(), os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not chat or not tok:
        print("NOTIFY_SKIPPED (optional; put it in your reply to the user instead)")
        return 0
    base = os.environ.get("DEVX_TELEGRAM_API", "https://api.telegram.org")
    try:
        data = urllib.parse.urlencode({"chat_id": chat, "text": a.text}).encode()
        with urllib.request.urlopen(urllib.request.Request(f"{base}/bot{tok}/sendMessage", data=data), timeout=20) as r:
            ok = bool(json.loads(r.read()).get("ok"))
    except Exception as e:  # noqa: BLE001
        ok = False
        print("NOTIFY_FAILED " + str(e).replace(tok, "***")[:80])
        return 0
    print("NOTIFY_OK" if ok else "NOTIFY_FAILED (is /start sent to the bot from that chat?)")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("env")
    t = sp.add_parser("task")
    t.add_argument("title")
    t.add_argument("--fresh", action="store_true")
    sp.add_parser("step").add_argument("task")
    sp.add_parser("enqueue").add_argument("titles", nargs="*")
    sp.add_parser("next")
    sp.add_parser("status")
    r = sp.add_parser("reset")
    r.add_argument("--queue", action="store_true")
    sp.add_parser("notify").add_argument("text")
    d = sp.add_parser("domain")
    d.add_argument("op", choices=["get", "set", "refresh"])
    d.add_argument("source", nargs="?")
    d.add_argument("url", nargs="?")
    lg = sp.add_parser("log")
    lg.add_argument("stage")
    lg.add_argument("code")
    lg.add_argument("detail", nargs="?")
    a = ap.parse_args(argv)
    f = {"env": cmd_env, "task": cmd_task, "step": cmd_step, "enqueue": cmd_enqueue, "next": cmd_next,
         "status": cmd_status, "reset": cmd_reset, "notify": cmd_notify, "domain": cmd_domain, "log": cmd_log}[a.cmd]
    return f(a) or 0


if __name__ == "__main__":
    sys.exit(main())
