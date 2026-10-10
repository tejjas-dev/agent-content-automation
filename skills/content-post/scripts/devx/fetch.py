"""Tiered fetching. http -> dynamic (browser, JS) -> stealth (Cloudflare solver).

Scrapling is used when installed (lazy import, so everything else works without it).
Plain-urllib is the http-tier fallback. Every tier returns a Fetched, never raises.
"""
from __future__ import annotations

import re
import urllib.error
import urllib.request
from dataclasses import dataclass, replace

from . import config
from .profile import TIERS

_CHALLENGE = re.compile(r"just a moment|checking your browser|cf-challenge|attention required|"
                        r"enable javascript and cookies|cf_chl_|ddos protection by", re.I)


@dataclass
class Fetched:
    ok: bool
    html: str = ""
    url: str = ""
    status: int = 0
    tier: str = ""
    reason: str = ""     # blocked|loading|empty|http|network|engine|engine_missing|invalid
    error: str = ""


class Ladder:
    """Attempt counter shared by all fetches of one source (max 4, as in the old skill)."""
    def __init__(self, max_attempts: int = 4):
        self.max = max_attempts
        self.attempts = 0


def looks_blocked(status: int, html: str) -> bool:
    head = html[:8000]
    if _CHALLENGE.search(head) and len(html) < 40000:
        return True
    return status in (403, 429, 503) and len(html) < 3000


def looks_loading(html: str) -> bool:
    return bool(re.search(r">\s*loading\.{0,3}\s*<", html, re.I)) and html.count("<a ") < 10


def _html_of(r) -> str:
    for attr in ("html_content", "body", "text"):
        v = getattr(r, attr, None)
        if isinstance(v, bytes):
            return v.decode("utf-8", "replace")
        if isinstance(v, str) and v:
            return v
    return str(r)


def _urllib(url: str, timeout: float):
    req = urllib.request.Request(url, headers={
        "User-Agent": config.UA, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9", "Accept-Encoding": "identity"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data, status, final = r.read(3_000_000), r.status, r.geturl()
            cs = r.headers.get_content_charset()
    except urllib.error.HTTPError as e:
        data, status, final, cs = e.read(500_000), e.code, url, None
    return status, data.decode(cs or "utf-8", "replace"), final


def _tier_http(url: str, timeout: float, wait: str):
    try:
        from scrapling.fetchers import Fetcher
    except ImportError:
        return _urllib(url, timeout)
    try:
        r = Fetcher.get(url, timeout=timeout)
        return int(getattr(r, "status", 200)), _html_of(r), str(getattr(r, "url", url) or url)
    except Exception:  # noqa: BLE001  - engine hiccup: degrade to urllib instead of failing
        return _urllib(url, timeout)


def _tier_dynamic(url: str, timeout: float, wait: str):
    from scrapling.fetchers import DynamicFetcher   # ImportError -> engine_missing
    kw = {"headless": True, "network_idle": True, "timeout": int(timeout * 1000)}
    if wait:
        kw["wait_selector"] = wait
    r = DynamicFetcher.fetch(url, **kw)
    return int(getattr(r, "status", 200)), _html_of(r), str(getattr(r, "url", url) or url)


def _tier_stealth(url: str, timeout: float, wait: str):
    from scrapling.fetchers import StealthyFetcher
    kw = {"headless": True, "network_idle": True, "solve_cloudflare": True,
          "timeout": int(max(timeout, 60) * 1000)}
    r = StealthyFetcher.fetch(url, **kw)
    return int(getattr(r, "status", 200)), _html_of(r), str(getattr(r, "url", url) or url)


_TIER_FN = {"http": _tier_http, "dynamic": _tier_dynamic, "stealth": _tier_stealth}


def _one(url: str, tier: str, timeout: float, wait: str) -> Fetched:
    try:
        status, html, final = _TIER_FN[tier](url, timeout, wait)
    except ImportError as e:
        return Fetched(False, tier=tier, reason="engine_missing", error=str(e)[:200])
    except urllib.error.URLError as e:
        return Fetched(False, tier=tier, reason="network", error=config.redact(e)[:200])
    except Exception as e:  # noqa: BLE001
        return Fetched(False, tier=tier, reason="engine", error=config.redact(e)[:200])
    r = Fetched(True, html, final, status, tier)
    if looks_blocked(status, html):
        return replace(r, ok=False, reason="blocked")
    if status >= 400:
        return replace(r, ok=False, reason="http")
    if len(html) < 200:
        return replace(r, ok=False, reason="empty")
    if looks_loading(html):
        return replace(r, ok=False, reason="loading")
    return r


def _should_escalate(r: Fetched, tier: str) -> bool:
    """Go to a heavier tier only when a heavier tier can actually help."""
    if r.reason in ("blocked", "empty", "loading", "invalid"):
        return True
    if r.reason == "http":
        return r.status in (403, 429)
    return r.reason == "engine" and tier != "http"      # network/404/missing engine: stop here


def fetch_page(url: str, start: str = "http", wait: str = "", ladder: Ladder | None = None,
               timeout: float = 30, validator=None) -> Fetched:
    """Escalate only as needed. `validator(html)->bool` lets callers reject useless pages."""
    ladder = ladder or Ladder()
    last = Fetched(False, reason="no_attempt")
    for tier in TIERS[TIERS.index(start):]:
        for k in range(2 if tier == "dynamic" else 1):
            if ladder.attempts >= ladder.max:
                return last
            ladder.attempts += 1
            r = _one(url, tier, timeout * (1 + k), wait)
            if r.ok and validator and not validator(r.html):
                r = replace(r, ok=False, reason="invalid")
            last = r
            if r.ok:
                return r
            if not (r.reason in ("loading", "invalid") and tier == "dynamic" and k == 0):
                break                                   # no point retrying this tier
        if not _should_escalate(last, tier):
            return last
    return last
