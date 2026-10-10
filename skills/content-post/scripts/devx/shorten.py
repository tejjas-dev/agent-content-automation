"""AroLinks link shortening. Token comes from env only and is never printed."""
from __future__ import annotations

import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from . import config

PREFIX = "https://arolinks.com/"


def _one(url: str) -> str:
    q = urllib.parse.urlencode({"api": config.env("AROLINKS_TOKEN"), "url": url, "format": "text"})
    req = urllib.request.Request(f"{config.arolinks_api()}?{q}", headers={"User-Agent": config.UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            out = r.read(2000).decode("utf-8", "replace").strip()
    except Exception:  # noqa: BLE001  (message may embed the token URL; never surface it)
        return ""
    return out if out.startswith(PREFIX) else ""


def shorten_all(urls: list[str], workers: int = 3) -> list[str]:
    """Same order as input; "" for a link that still failed after one retry."""
    with ThreadPoolExecutor(max_workers=workers) as ex:
        res = list(ex.map(_one, urls))
    return [r or _one(u) for r, u in zip(res, urls)]
