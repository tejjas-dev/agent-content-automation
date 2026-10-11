#!/usr/bin/env python3
"""Fetch ONE page and save its HTML.   fetch.py URL OUT.html [--tier http|dynamic|stealth] [--wait CSS] [--timeout SEC]
Run it with $PY (the Scrapling venv python from `drama.py env`). Prints one line: OK ... / FAIL ...
  http     plain request (falls back to urllib when Scrapling is not installed)
  dynamic  real browser, JavaScript, waits for network idle (JS-rendered search results)
  stealth  Cloudflare Turnstile solver (~15 s)  <- katdrama
Exit 0 = ok, 1 = failed."""
import argparse
import re
import sys
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
CHALLENGE = re.compile(r"just a moment|checking your browser|cf-challenge|attention required|enable javascript and cookies|cf_chl_", re.I)


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


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("out")
    ap.add_argument("--tier", default="http", choices=["http", "dynamic", "stealth"])
    ap.add_argument("--wait", default="")
    ap.add_argument("--timeout", type=float, default=30)
    a = ap.parse_args(argv)
    try:
        status, html, final = get(a.url, a.tier, a.wait, a.timeout)
    except ImportError:
        print(f"FAIL tier={a.tier} reason=scrapling_missing (run drama-post/scripts/setup.sh and use $PY)")
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"FAIL tier={a.tier} reason={type(e).__name__}: {str(e)[:100]}")
        return 1
    blocked = (bool(CHALLENGE.search(html[:8000])) and len(html) < 40000) or (status in (403, 429, 503) and len(html) < 3000)
    if blocked or status >= 400 or len(html) < 200:
        hint = " (try --tier stealth)" if blocked and a.tier != "stealth" else ""
        print(f"FAIL tier={a.tier} status={status} reason={'blocked' if blocked else 'bad_response'}{hint}")
        return 1
    open(a.out, "w", encoding="utf-8").write(html)
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    title = re.sub(r"\s+", " ", m.group(1)).strip()[:70] if m else ""
    print(f"OK tier={a.tier} status={status} bytes={len(html)} url={final} title={title!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
