"""Command line: run | doctor | setup | probe | profiles | profile-apply | version."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from . import config, content_types, store
from . import profile as pf
from .pipeline import Result, Runner

LIGHT = ["beautifulsoup4>=4.12", "lxml>=5"]
FULL = LIGHT + ["scrapling[fetchers]>=0.4"]


def _spec(name: str):
    spec = content_types.get(name)
    if spec is None:
        print(f"❌ Unknown type '{name}'. Available: {', '.join(content_types.available())}")
        sys.exit(2)
    return spec


# ---- run ---------------------------------------------------------------------------------
def cmd_run(a) -> int:
    spec = _spec(a.type)
    seen, titles = set(), []
    for t in a.titles:
        t = " ".join(t.split())
        if t and t.lower() not in seen:
            seen.add(t.lower())
            titles.append(t)
    if not titles:
        print("❌ Koi title nahi mila.")
        return 2
    if not a.dry_run:
        missing = [n for n in (*config.SECRET_ENVS, spec.channels_env) if not config.env(n)]
        if missing:
            print(f"⚙️ Setup adhura hai: {', '.join(missing)}.")
            return 0
    max_n = a.max or config.DEFAULT_MAX_TITLES
    budget = a.budget or config.number("DEVX_BUDGET", 420)
    start, counts = time.time(), {"ok": 0, "fail": 0, "skip": 0}
    try:
        with store.run_lock(config.number("DEVX_LOCK_WAIT", 120)):
            store.prune_stale()
            runner = Runner(spec, force=a.force, dry=a.dry_run)
            done = 0
            for i, t in enumerate(titles):
                if i >= max_n:
                    print(f"⏭️ {t}: limit ({max_n}) se aage, skip."); counts["skip"] += 1
                    continue
                elapsed = time.time() - start
                if i > 0 and elapsed + max(elapsed / done, 60) > budget:
                    print(f"⏭️ {t}: time budget khatam, dobara bhejo."); counts["skip"] += 1
                    continue
                res: Result = runner.run_title(t)
                done += 1
                print(res.line(), flush=True)
                if a.dry_run and res.preview:
                    print("--- caption preview ---\n" + res.preview.rstrip() + "\n-----------------------")
                counts["ok" if res.code in ("OK", "DRYRUN_OK", "ALREADY_POSTED") else "fail"] += 1
                if i < len(titles) - 1:
                    time.sleep(config.number("DEVX_TITLE_DELAY", 2))
    except store.Busy:
        print("⏳ Dusra run chal raha hai, thodi der baad try karo.")
        return 0
    print(f"Summary: {counts['ok']} ok, {counts['fail']} fail, {counts['skip']} skip.")
    return 0


# ---- doctor ------------------------------------------------------------------------------
def cmd_doctor(a) -> int:
    spec = _spec(a.type)
    bad = 0

    def row(ok, name, hint=""):
        nonlocal bad
        bad += 0 if ok else 1
        print(f"{'ok  ' if ok else 'FAIL'} {name}{(' — ' + hint) if hint and not ok else ''}")

    row(sys.version_info >= (3, 10), "python>=3.10", sys.version.split()[0])
    for mod in ("bs4", "lxml", "soupsieve"):
        try:
            __import__(mod); row(True, mod)
        except ImportError:
            row(False, mod, "run: content_post.py setup --light")
    try:
        __import__("scrapling.fetchers"); print("ok   scrapling (dynamic/stealth tiers available)")
    except ImportError:
        print("info scrapling not installed: only the plain http tier works (run: setup)")
    cache = Path.home() / ".cache" / "ms-playwright"
    print(f"info browsers {'found' if cache.exists() and any(cache.iterdir()) else 'not found'} (needed only for JS/Cloudflare sites)")
    try:
        config.data_dir(); row(True, f"data dir {config.data_dir()}")
    except OSError as e:
        row(False, "data dir", str(e))
    for n in (*config.SECRET_ENVS, spec.channels_env):
        row(bool(config.env(n)), f"env {n}", "not set")
    profs = pf.effective_profiles(spec.name)
    row(bool(profs), f"profiles ({', '.join(f'{p.id}:{p.origin}' for p in profs) or 'none'})")
    if not a.offline and config.env("TELEGRAM_BOT_TOKEN"):
        from . import telegram
        row(telegram.get_me(), "telegram bot token", "getMe failed (wrong token or no internet)")
        for ch in config.channels(spec.channels_env):
            row(telegram.get_chat(ch), f"channel {ch}", "wrong id, or bot is not admin there")
    print("READY" if not bad else "NOT READY")
    return 1 if bad else 0


# ---- setup -------------------------------------------------------------------------------
def cmd_setup(a) -> int:
    reqs = LIGHT if a.light else FULL
    venv = config.data_dir() / "venv"
    py = config.venv_python()
    if not py.exists():
        r = subprocess.run([sys.executable, "-m", "venv", str(venv)], capture_output=True, text=True)
        if r.returncode != 0:
            print("venv failed (" + r.stderr.strip()[-120:] + "); falling back to pip --user")
            r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--user",
                                "--break-system-packages", *reqs])
            if r.returncode != 0:
                print("SETUP_NEEDED: pip install failed. Try: apt-get install -y python3-venv python3-pip")
                return 1
            py = Path(sys.executable)
    if py != Path(sys.executable):
        r = subprocess.run([str(py), "-m", "pip", "install", "-q", "-U", *reqs])
        if r.returncode != 0:
            print("SETUP_NEEDED: pip install failed (network?)")
            return 1
    if not a.light:
        scr = py.parent / "scrapling"
        cmd = [str(scr), "install"] if scr.exists() else [str(py), "-m", "scrapling", "install"]
        r = subprocess.run(cmd, timeout=1500)
        if r.returncode != 0:
            print("SETUP_PARTIAL: python deps ok, `scrapling install` (browsers) failed — "
                  "http tier still works. Re-run `setup` or check root/apt access.")
            return 1
    print("SETUP_OK " + ("light" if a.light else "full"))
    return 0


# ---- probe / profiles / profile-apply -----------------------------------------------------
def cmd_probe(a) -> int:
    from . import fetch
    from .dom import parse
    r = fetch.fetch_page(a.url, a.tier, ladder=fetch.Ladder(1))
    soup = parse(r.html) if r.html else None
    print(json.dumps({"ok": r.ok, "tier": r.tier, "status": r.status, "reason": r.reason,
                      "error": r.error, "final_url": r.url, "bytes": len(r.html),
                      "anchors": len(soup.find_all("a")) if soup else 0,
                      "title": soup.title.get_text(strip=True)[:100] if soup and soup.title else ""}))
    return 0 if r.ok else 1


def cmd_profiles(a) -> int:
    for p in pf.effective_profiles(_spec(a.type).name):
        print(f"{p.id}\torigin={p.origin}\torder={p.data['order']}\tentry={p.data['entry_urls'][0]}")
    return 0


def cmd_apply(a) -> int:
    spec = _spec(a.type)
    try:
        cand = json.loads(Path(a.file).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"REJECTED: cannot read JSON ({e})")
        return 1
    cand["id"] = a.source
    cand.setdefault("type", spec.name)
    ok, errs = pf.validate(cand)
    if not ok:
        print("REJECTED: " + "; ".join(errs))
        return 1
    try:
        with store.run_lock(config.number("DEVX_LOCK_WAIT", 120)):
            res = Runner(spec, dry=True, profiles=[pf.Prof(a.source, pf.merge(cand), "candidate")]).run_title(a.title)
    except store.Busy:
        print("REJECTED: another run is in progress")
        return 1
    if res.code != "DRYRUN_OK":
        print(f"REJECTED: test run gave {res.code} {res.detail}".strip())
        return 1
    f = pf.save_override(spec.name, cand)
    print(f"APPLIED: {a.source} saved as override ({f.name}). Now rerun the title once.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="content_post.py")
    sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("run"); r.add_argument("type"); r.add_argument("titles", nargs="+")
    r.add_argument("--force", action="store_true"); r.add_argument("--dry-run", action="store_true")
    r.add_argument("--max", type=int); r.add_argument("--budget", type=float)
    d = sp.add_parser("doctor"); d.add_argument("type", nargs="?", default="drama"); d.add_argument("--offline", action="store_true")
    s = sp.add_parser("setup"); s.add_argument("--light", action="store_true")
    p = sp.add_parser("probe"); p.add_argument("url"); p.add_argument("--tier", default="http", choices=pf.TIERS)
    l = sp.add_parser("profiles"); l.add_argument("type", nargs="?", default="drama")
    x = sp.add_parser("profile-apply"); x.add_argument("type"); x.add_argument("source")
    x.add_argument("--file", required=True); x.add_argument("--title", required=True)
    sp.add_parser("version")
    a = ap.parse_args(argv)
    if a.cmd == "version":
        print(config.VERSION); return 0
    return {"run": cmd_run, "doctor": cmd_doctor, "setup": cmd_setup, "probe": cmd_probe,
            "profiles": cmd_profiles, "profile-apply": cmd_apply}[a.cmd](a)
