#!/usr/bin/env python3
"""Health check:  doctor.py [--net]
--net also tests: Telegram bot + channels + notify chat, the AroLinks token (shortens https://example.com once = 1 test link),
and the sources (primary / fallback / finder reachable; a Cloudflare 403 counts as alive).
Exit 0 = READY, 1 = NOT READY (fallback site down is only a warning)."""
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).absolute().parents[2]            # .../skills
NEEDED = ["drama-post", "drama-find", "drama-scrape", "link-short", "drama-format", "drama-verify", "telegram-send", "content-cleanup"]
PIN = os.environ.get("DEVX_SCRAPLING_VERSION", "0.4.15")
bad = 0


def row(ok, name, hint=""):
    global bad
    bad += 0 if ok else 1
    print(("ok   " if ok else "FAIL ") + name + ("" if ok or not hint else " - " + hint))


def warn(ok, name, hint=""):
    print(("ok   " if ok else "warn ") + name + ("" if ok or not hint else " - " + hint))


def env(name):
    return os.environ.get(name, "").strip()


def data_dir():
    e = os.environ.get("DEVX_DATA_DIR")
    if e:
        return Path(e)
    w = Path("/workspace")
    return w if w.is_dir() and os.access(w, os.W_OK) else Path.home() / ".devx-content"


row(sys.version_info >= (3, 8), "python>=3.8", sys.version.split()[0])
row(all((HERE / n / "SKILL.md").exists() for n in NEEDED), "all 8 skills installed side by side", f"missing under {HERE}")
for v in ("AROLINKS_TOKEN", "TELEGRAM_BOT_TOKEN", "DRAMA_POST_CHANNEL_IDS"):
    raw = os.environ.get(v, "")
    row(bool(raw.strip()), f"env {v}", "not set (profile .env / agent env)")
    if raw.strip() and raw != raw.strip():
        warn(False, f"env {v} has leading/trailing whitespace", "scripts strip it, but fix the .env line")
    if raw.strip() and re.search(r"""^["'].*["']$""", raw.strip()):
        warn(False, f"env {v} is wrapped in quotes", "remove the quotes in the .env value")
chans = [c for c in re.split(r"[,;\s]+", env("DRAMA_POST_CHANNEL_IDS")) if c]
if chans:
    warn(all(re.fullmatch(r"-?\d+|@\w+", c) for c in chans), f"channel id format ({len(chans)} channel(s))", "use -100... ids (or @name), comma separated")
print(("ok   " if env("DEVX_NOTIFY_CHAT_ID") else "info ") + "env DEVX_NOTIFY_CHAT_ID (optional: private Telegram alerts; without it alerts go in the agent's reply)")
data = data_dir()
try:
    (data / "drama" / "work").mkdir(parents=True, exist_ok=True)
    (data / "drama" / "state").mkdir(parents=True, exist_ok=True)
    row(os.access(data / "drama", os.W_OK), f"drama folder {data / 'drama'} (work/ = cleaned after 24 h, state/ = kept)")
except OSError as e:
    row(False, "drama folder", str(e))
venvs = [data / "venv" / "bin" / "python", Path.home() / ".devx-content" / "venv" / "bin" / "python"]
py = next((v for v in venvs if v.exists()), None)
if py is not None:
    try:
        ver = subprocess.run([str(py), "-c", "import importlib.metadata as m;print(m.version('scrapling'))"], capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        ver = ""
    row(bool(ver), f"scrapling in venv {py.parent.parent}", "run: sh scripts/setup.sh")
    if ver:
        warn(ver == PIN, f"scrapling version {ver} (pinned {PIN})", "run: sh scripts/setup.sh (or set DEVX_SCRAPLING_VERSION)")
else:
    try:
        import scrapling  # noqa: F401
        print("ok   scrapling (system python)")
    except ImportError:
        row(False, "scrapling", "run: sh scripts/setup.sh")
try:
    sys.path.insert(0, str(Path(__file__).absolute().parent))
    import proposal
    s = proposal.summary()
    if s:
        print(f"info draft updates: {s} (python3 scripts/proposal.py list)")
except Exception:  # noqa: BLE001
    pass
if "--net" in sys.argv:
    tg = env("TELEGRAM_BOT_TOKEN")
    if tg:
        base = os.environ.get("DEVX_TELEGRAM_API", "https://api.telegram.org") + "/bot" + tg

        def ok(method, **kw):
            try:
                with urllib.request.urlopen(f"{base}/{method}?{urllib.parse.urlencode(kw)}", timeout=20) as r:
                    return bool(json.loads(r.read()).get("ok"))
            except Exception:  # noqa: BLE001
                return False
        row(ok("getMe"), "telegram bot token", "getMe failed (wrong token / no internet)")
        for ch in chans:
            row(ok("getChat", chat_id=ch), f"channel {ch}", "wrong id or bot is not admin there")
        if env("DEVX_NOTIFY_CHAT_ID"):
            row(ok("getChat", chat_id=env("DEVX_NOTIFY_CHAT_ID")), "notify chat", "send /start to the bot from that chat first")
    if env("AROLINKS_TOKEN"):
        try:
            q = urllib.parse.urlencode({"api": env("AROLINKS_TOKEN"), "url": "https://example.com", "format": "text"})
            with urllib.request.urlopen(urllib.request.Request(os.environ.get("DEVX_AROLINKS_API", "https://arolinks.com/api") + "?" + q,
                                                               headers={"User-Agent": "Mozilla/5.0"}), timeout=25) as r:
                good = r.read(500).decode("utf-8", "replace").strip().startswith("https://arolinks.com/")
        except Exception:  # noqa: BLE001
            good = False
        row(good, "arolinks token (made 1 test link for example.com)", "token rejected or AroLinks unreachable")
    try:
        import drama
        dom = drama.domains()
        for key, must in (("primary", True), ("fallback", False), ("finder", False)):
            state, final, why = drama.probe(dom[key])
            line = f"site {key} {dom[key]} ({state}, {why})"
            if key == "primary":
                row(state == "ok", line, "run: python3 scripts/drama.py domain refresh")
            else:
                warn(state in ("ok", "moved"), line, "check later; the fallback/finder are only used when needed")
    except Exception as e:  # noqa: BLE001
        warn(False, "site checks", type(e).__name__)
print("READY" if not bad else "NOT READY")
sys.exit(1 if bad else 0)
