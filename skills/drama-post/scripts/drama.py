#!/usr/bin/env python3
"""Helper for the drama pipeline: paths, queue, notify, domains. Stdlib only.

  drama.py env                       SK / PY / DATA / ROOT as key=value (also migrates old data once)
  drama.py task "<title>"            create ROOT/work/<utc>-<slug>, print its path
  drama.py enqueue "A" "B" ...       add titles (max 5 per call), print RUNNER or QUEUED position=N
                                     (no titles = resume a stuck queue)
  drama.py next                      RUNNER only: print the next title, or EMPTY (and give up the runner role)
  drama.py status | reset [--queue]
  drama.py notify "text"             private Telegram message to DEVX_NOTIFY_CHAT_ID (best effort)
  drama.py domain get|set <source> [url]

Layout: DATA = $DEVX_DATA_DIR, else /workspace if writable, else ~/.devx-content
  DATA/drama/work/    per-drama task folders (everything temporary; cleaned by content-cleanup)
  DATA/drama/state/   kept: queue.jsonl, runner.json, posted.jsonl, domains.json, learned/<source>.md
"""
import argparse
import json
import os
import re
import shutil
import sys
import time
import urllib.parse
import urllib.request
from contextlib import contextmanager
from pathlib import Path

try:
    import fcntl
except ImportError:
    fcntl = None

SKILLS = Path(__file__).resolve().parents[2]
LEGACY = Path.home() / ".devx-content"
DEFAULT_DOMAINS = {"katworld": "https://katworld.net/?type=KatDrama", "katdrama": "https://new.katdrama.my/"}
MAX_BATCH = 5


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
    p = sub("state") / "queue.jsonl"
    try:
        return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    except (OSError, ValueError):
        return []


def write_q(items):
    (sub("state") / "queue.jsonl").write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items), encoding="utf-8")


def get_runner():
    try:
        return json.loads((sub("state") / "runner.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def set_runner(d):
    p = sub("state") / "runner.json"
    if d is None:
        p.unlink(missing_ok=True)
    else:
        p.write_text(json.dumps(d), encoding="utf-8")


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
            else:
                q.insert(0, {"title": r["current"], "retried": True})
        ahead = len(q) + (1 if active and r.get("current") else 0)
        q += [{"title": t, "ts": int(time.time())} for t in added]
        write_q(q)
        for t in dups:
            print(f"DUPLICATE {t}")
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


def cmd_status(a):
    r = get_runner()
    print(f"runner={'active' if alive(r) else 'idle'} current={r.get('current', '')!r} queued={len(read_q())}")


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
    print(f"SK={SKILLS}\nPY={scrapling_python()}\nDATA={data_dir()}\nROOT={data_dir() / 'drama'}")


def cmd_task(a):
    slug = re.sub(r"[^a-z0-9]+", "-", a.title.lower()).strip("-")[:40] or "x"
    p = sub("work") / f"{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}-{slug}"
    p.mkdir(parents=True, exist_ok=True)
    print(p)


# ---- domains / notify -----------------------------------------------------------------------
def domains():
    d = dict(DEFAULT_DOMAINS)
    try:
        d.update(json.loads((sub("state") / "domains.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return d


def cmd_domain(a):
    d = domains()
    if a.op == "get":
        if a.source not in d:
            print(f"ERROR unknown source {a.source} (known: {', '.join(d)})")
            return 2
        print(d[a.source])
        return 0
    if not a.url or not a.url.startswith("https://"):
        print("ERROR give an https:// URL")
        return 2
    custom = {k: v for k, v in d.items() if v != DEFAULT_DOMAINS.get(k)}
    custom[a.source] = a.url
    (sub("state") / "domains.json").write_text(json.dumps(custom, indent=1), encoding="utf-8")
    print(f"saved {a.source} = {a.url}")
    return 0


def cmd_notify(a):
    chat, tok = os.environ.get("DEVX_NOTIFY_CHAT_ID", ""), os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not chat or not tok:
        print("NOTIFY_SKIPPED (set DEVX_NOTIFY_CHAT_ID; tell the user in your reply instead)")
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
    sp.add_parser("task").add_argument("title")
    sp.add_parser("enqueue").add_argument("titles", nargs="*")
    sp.add_parser("next")
    sp.add_parser("status")
    r = sp.add_parser("reset")
    r.add_argument("--queue", action="store_true")
    sp.add_parser("notify").add_argument("text")
    d = sp.add_parser("domain")
    d.add_argument("op", choices=["get", "set"])
    d.add_argument("source")
    d.add_argument("url", nargs="?")
    a = ap.parse_args(argv)
    f = {"env": cmd_env, "task": cmd_task, "enqueue": cmd_enqueue, "next": cmd_next, "status": cmd_status,
         "reset": cmd_reset, "notify": cmd_notify, "domain": cmd_domain}[a.cmd]
    return f(a) or 0


if __name__ == "__main__":
    sys.exit(main())
