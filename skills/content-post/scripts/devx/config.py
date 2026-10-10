"""Paths, env access and shared constants. Stdlib only."""
from __future__ import annotations

import os
import re
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[2]
_vf = SKILL_DIR / "VERSION"
VERSION = _vf.read_text().strip() if _vf.exists() else "0.0.0"

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0.0.0 Safari/537.36")
SECRET_ENVS = ("AROLINKS_TOKEN", "TELEGRAM_BOT_TOKEN")
CAPTION_LIMIT = 950          # Telegram hard limit is 1024 UTF-16 units
MAX_LINKS_PER_POST = 12
DEFAULT_MAX_TITLES = 5
POSTER_MAX_BYTES = 5 * 1024 * 1024


def env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def number(name: str, default: float) -> float:
    try:
        return float(env(name, str(default)))
    except ValueError:
        return default


def sources_dir() -> Path:
    return Path(env("DEVX_SOURCES_DIR") or (SKILL_DIR / "sources"))


def data_dir() -> Path:
    p = Path(env("DEVX_DATA_DIR") or (Path.home() / ".devx-content"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def sub(name: str) -> Path:
    p = data_dir() / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def venv_python() -> Path:
    return data_dir() / "venv" / "bin" / "python"


def channels(env_name: str) -> list[str]:
    return [c for c in re.split(r"[,;\s]+", env(env_name)) if c]


def redact(text: object) -> str:
    s = str(text)
    for name in SECRET_ENVS:
        v = env(name)
        if v:
            s = s.replace(v, "***")
    return s


def allow_http() -> bool:      # tests only
    return env("DEVX_TEST_ALLOW_HTTP") == "1"


def arolinks_api() -> str:
    return env("DEVX_AROLINKS_API", "https://arolinks.com/api")


def telegram_api() -> str:
    return env("DEVX_TELEGRAM_API", "https://api.telegram.org")
