#!/usr/bin/env python3
"""Fetch ONE page and save its HTML.   fetch.py URL OUT.html [--tier auto|http|dynamic|stealth] [--wait CSS] [--timeout SEC]
Run it with $PY (the Scrapling venv python from `drama.py env`). Prints one line: OK ... / FAIL ... code=<CODE>
  http     plain request (falls back to urllib when Scrapling is not installed)
  dynamic  real browser, JavaScript, waits for network idle (JS-rendered search results)  <- primary site search
  stealth  Cloudflare Turnstile solver (~15 s)                                           <- fallback site
  auto     http -> dynamic -> stealth: climbs by itself when blocked or when the page is only a JavaScript shell
Transient errors (timeout, 429, 5xx) are retried with exponential backoff: DEVX_RETRIES attempts per tier (default 2),
DEVX_BACKOFF base seconds (default 2, cap DEVX_BACKOFF_CAP=30). auto stops after --max-attempts (default 4).
Codes: BLOCKED NOT_FOUND TIMEOUT ERROR NOT_INSTALLED BAD_RESPONSE HTTP_<n> JS_SHELL ATTEMPTS_EXHAUSTED (see drama-post/references/recovery.md).
Exit 0 = ok, 1 = failed."""
import argparse
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
CHALLENGE = re.compile(r"just a moment|checking your browser|cf-challenge|attention required|enable javascript and cookies|cf_chl_", re.I)
TIERS = ["http", "dynamic", "stealth"]


class Fail(Exception):
    def __init__(self, code, reason, status=0, retry=False, escalate=False):
        super().__init__(reason)
        self.code, self.reason, self.status, self.retry, self.escalate = code, reason, status, retry, escalate


def log_event(code, detail=""):
    """Best-effort line in <DATA>/drama/state/logs/events.jsonl (same format as drama.py log)."""
    try:
        e = os.environ.get("DEVX_DATA_DIR")
        root = Path(e) if e else (Path("/workspace") if os.path.isdir("/workspace") and os.access("/workspace", os.W_OK) else Path.home() / ".devx-content")
        d = root / "drama" / "state" / "logs"
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "events.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": int(time.time()), "stage": "fetch", "code": code, "detail": detail[:200]}) + "\n")
    except Exception:  # noqa: BLE001
        pass


def backoff(n):
    base, cap = float(os.environ.get("DEVX_BACKOFF", "2")), float(os.environ.get("DEVX_BACKOFF_CAP", "30"))
    time.sleep(min(cap, base * 2 ** n) * (0.5 + random.random() / 2) if base > 0 else 0)


def html_of(r):
    for attr in ("html_content", "body", "text"):
        v = getattr(r, attr, None)
        if isinstance(v, bytes):
            return v.decode("utf-8", "replace")
        if isinstance(v, str) and v:
            return v
    return str(r)


def get(url, tier, wait, timeout):
    if tier == "http":
        try:
            from scrapling.fetchers import Fetcher
            r = Fetcher.get(url, timeout=timeout)
            return int(getattr(r, "status", 200)), html_of(r), str(getattr(r, "url", url) or url)
        except Exception:  # noqa: BLE001  not installed or engine hiccup -> plain urllib
            pass
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.read(3_000_000).decode(r.headers.get_content_charset() or "utf-8", "replace"), r.geturl()
        except urllib.error.HTTPError as e:
            return e.code, e.read(500_000).decode("utf-8", "replace"), url
    from scrapling import fetchers
    if tier == "dynamic":
        kw = {"headless": True, "network_idle": True, "timeout": int(timeout * 1000)}
        if wait:
            kw["wait_selector"] = wait
        r = fetchers.DynamicFetcher.fetch(url, **kw)
    else:
        r = fetchers.StealthyFetcher.fetch(url, headless=True, network_idle=True, solve_cloudflare=True,
                                           timeout=int(max(timeout, 60) * 1000))
    return int(getattr(r, "status", 200)), html_of(r), str(getattr(r, "url", url) or url)


def js_shell(html):
    """True when the page is only a JavaScript placeholder ("Loading..."): results are not in the HTML yet."""
    t = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", html)
    t = re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", t)).strip()
    return len(t) < 300 and bool(re.search(r"loading|please wait|enable javascript", t, re.I))


def attempt(url, tier, wait, timeout):
    try:
        status, html, final = get(url, tier, wait, timeout)
    except ImportError:
        raise Fail("NOT_INSTALLED", "scrapling_missing (run drama-post/scripts/setup.sh and use $PY)")
    except Exception as e:  # noqa: BLE001
        slow = "timeout" in type(e).__name__.lower() or "timed out" in str(e).lower()
        raise Fail("TIMEOUT" if slow else "ERROR", f"{type(e).__name__}: {str(e)[:100]}", retry=True)
    blocked = (bool(CHALLENGE.search(html[:8000])) and len(html) < 40000) or (status in (403, 429, 503) and len(html) < 3000)
    if blocked:
        raise Fail("BLOCKED", "blocked", status, retry=status in (429, 503), escalate=True)
    if status in (404, 410):
        raise Fail("NOT_FOUND", "bad_response", status)
    if status == 429 or status >= 500:
        raise Fail(f"HTTP_{status}", "bad_response", status, retry=True)
    if status >= 400 or len(html) < 200:
        raise Fail("BAD_RESPONSE", "bad_response", status)
    return status, html, final


def run(url, tiers, wait, timeout, retries, max_attempts):
    used, last = 0, None
    for tier in tiers:
        for n in range(retries):
            if used >= max_attempts:
                raise Fail("ATTEMPTS_EXHAUSTED", f"gave up after {used} attempts (last {last.code if last else '?'})", getattr(last, "status", 0))
            used += 1
            try:
                status, html, final = attempt(url, tier, wait, timeout)
                if tier != tiers[-1] and js_shell(html):
                    last = Fail("JS_SHELL", "js_shell", status, escalate=True)
                    break
                return tier, status, html, final
            except Fail as f:
                last = f
                log_event(f.code, f"tier={tier} attempt={n + 1} {f.reason}")
                if f.retry and n + 1 < retries:
                    backoff(n)
                    continue
                break
        if not last.escalate or tier == tiers[-1]:
            break
    raise last


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("out")
    ap.add_argument("--tier", default="http", choices=["auto"] + TIERS)
    ap.add_argument("--wait", default="")
    ap.add_argument("--timeout", type=float, default=30)
    ap.add_argument("--max-attempts", type=int, default=4)
    a = ap.parse_args(argv)
    tiers = TIERS if a.tier == "auto" else [a.tier]
    retries = max(1, int(os.environ.get("DEVX_RETRIES", "2")))
    try:
        tier, status, html, final = run(a.url, tiers, a.wait, a.timeout, retries, a.max_attempts)
    except Fail as f:
        hint = " (try --tier stealth)" if f.code == "BLOCKED" and a.tier not in ("stealth", "auto") else ""
        if f.code == "JS_SHELL":
            hint = " (use --tier dynamic)"
        print(f"FAIL tier={a.tier} status={f.status} reason={f.reason}{hint} code={f.code}")
        return 1
    note = " note=js_shell(use --tier dynamic)" if js_shell(html) else ""
    tmp = a.out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(html)
    os.replace(tmp, a.out)
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    title = re.sub(r"\s+", " ", m.group(1)).strip()[:70] if m else ""
    print(f"OK tier={tier} status={status} bytes={len(html)} url={final} title={title!r}{note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
