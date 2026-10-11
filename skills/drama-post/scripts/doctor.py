#!/usr/bin/env python3
"""Health check:  doctor.py [--net]   (--net also tests the Telegram bot and channels)"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]            # .../skills
NEEDED = ["drama-post", "drama-find", "drama-scrape", "link-short", "drama-format", "drama-verify", "telegram-send", "content-cleanup"]
bad = 0


def row(ok, name, hint=""):
    global bad
    bad += 0 if ok else 1
    print(("ok   " if ok else "FAIL ") + name + ("" if ok or not hint else " - " + hint))


row(sys.version_info >= (3, 8), "python>=3.8", sys.version.split()[0])
row(all((HERE / n / "SKILL.md").exists() for n in NEEDED), "all 8 skills installed side by side", f"missing under {HERE}")
for v in ("AROLINKS_TOKEN", "TELEGRAM_BOT_TOKEN", "DRAMA_POST_CHANNEL_IDS"):
    row(bool(os.environ.get(v)), f"env {v}", "not set (profile .env / agent env)")
data = Path(os.environ.get("DEVX_DATA_DIR") or Path.home() / ".devx-content")
try:
    data.mkdir(parents=True, exist_ok=True)
    row(os.access(data, os.W_OK), f"data dir {data}")
except OSError as e:
    row(False, "data dir", str(e))
venv_py = data / "venv" / "bin" / "python"
try:
    import scrapling  # noqa: F401
    print("ok   scrapling (system python)")
except ImportError:
    row(venv_py.exists(), "scrapling (venv)", "run: sh scripts/setup.sh")
if "--net" in sys.argv and os.environ.get("TELEGRAM_BOT_TOKEN"):
    base = os.environ.get("DEVX_TELEGRAM_API", "https://api.telegram.org") + "/bot" + os.environ["TELEGRAM_BOT_TOKEN"]

    def ok(method, **kw):
        try:
            with urllib.request.urlopen(f"{base}/{method}?{urllib.parse.urlencode(kw)}", timeout=20) as r:
                return bool(json.loads(r.read()).get("ok"))
        except Exception:  # noqa: BLE001
            return False
    row(ok("getMe"), "telegram bot token", "getMe failed (wrong token / no internet)")
    for ch in [c for c in re.split(r"[,;\s]+", os.environ.get("DRAMA_POST_CHANNEL_IDS", "")) if c]:
        row(ok("getChat", chat_id=ch), f"channel {ch}", "wrong id or bot is not admin there")
print("READY" if not bad else "NOT READY")
sys.exit(1 if bad else 0)
