#!/usr/bin/env python3
"""Shorten every link in ONE run (AroLinks). Order and label pairing are preserved by index.

  shorten.py links.json [--out short.json] [--workers 4]
  links.json : [{"label": "480p Single Episode", "url": "https://..."}, ...]
  short.json : same list + "short": "https://arolinks.com/..." or null (failed)
Env: AROLINKS_TOKEN (never printed).  Exit: 0 if at least one link was shortened, 1 if none, 2 on bad input.
Failures are classified: auth (token rejected -> stop at once, retrying cannot help), rate, network, unknown, invalid_url.
Rate/network/unknown are retried with exponential backoff (DEVX_RETRIES rounds, default 2; DEVX_BACKOFF base seconds, default 2).
Prints  shortened X/Y -> path | failed: labels | reasons: auth=2   (+ a CODE= line for the reply: AUTH, RATE, NETWORK)
"""
import argparse
import json
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PREFIX = "https://arolinks.com/"
API = os.environ.get("DEVX_AROLINKS_API", "https://arolinks.com/api")
AUTH_WORDS = ("invalid api", "invalid token", "api key", "api token", "unauthorized", "authentication", "forbidden")
RATE_WORDS = ("rate limit", "too many", "limit exceeded", "limit reached")


def log_event(code, detail=""):
    try:
        e = os.environ.get("DEVX_DATA_DIR")
        root = Path(e) if e else (Path("/workspace") if os.path.isdir("/workspace") and os.access("/workspace", os.W_OK) else Path.home() / ".devx-content")
        d = root / "drama" / "state" / "logs"
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "events.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": int(time.time()), "stage": "shorten", "code": code, "detail": detail[:200]}) + "\n")
    except Exception:  # noqa: BLE001
        pass


def backoff(n):
    base, cap = float(os.environ.get("DEVX_BACKOFF", "2")), float(os.environ.get("DEVX_BACKOFF_CAP", "30"))
    time.sleep(min(cap, base * 2 ** n) * (0.5 + random.random() / 2) if base > 0 else 0)


def classify(text):
    low = text.lower()
    if any(w in low for w in AUTH_WORDS):
        return "auth"
    if any(w in low for w in RATE_WORDS):
        return "rate"
    return "unknown"


def shorten_one(url):
    """-> (short_url or None, reason). Error text can contain the token URL: it is never surfaced."""
    if not url.startswith(("http://", "https://")):
        return None, "invalid_url"
    q = urllib.parse.urlencode({"api": os.environ.get("AROLINKS_TOKEN", "").strip(), "url": url, "format": "text"})
    try:
        req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=25) as r:
            out = r.read(2000).decode("utf-8", "replace").strip()
    except urllib.error.HTTPError as e:
        return None, "auth" if e.code in (401, 403) else "rate" if e.code == 429 else "network"
    except Exception:  # noqa: BLE001
        return None, "network"
    return (out, "ok") if out.startswith(PREFIX) else (None, classify(out))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("links")
    ap.add_argument("--out")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args(argv)
    if not os.environ.get("AROLINKS_TOKEN", "").strip():
        print("ERROR: AROLINKS_TOKEN is not set")
        return 2
    try:
        with open(a.links, encoding="utf-8") as fh:
            items = json.load(fh)
        assert isinstance(items, list) and all(i.get("url") and "label" in i for i in items)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: bad links file ({type(e).__name__})")
        return 2
    urls = list(dict.fromkeys(i["url"] for i in items))          # same URL -> one API call
    with ThreadPoolExecutor(max_workers=max(1, a.workers)) as ex:
        res = dict(zip(urls, ex.map(shorten_one, urls)))
    rounds = max(1, int(os.environ.get("DEVX_RETRIES", "2")))
    for n in range(rounds):
        todo = [u for u, (s, why) in res.items() if not s and why not in ("auth", "invalid_url")]
        if not todo or any(why == "auth" for _, why in res.values()):   # auth: retrying only burns calls
            break
        backoff(n)
        for u in todo:
            res[u] = shorten_one(u)
    out = [{"label": i["label"], "url": i["url"], "short": res[i["url"]][0]} for i in items]
    path = a.out or os.path.join(os.path.dirname(os.path.abspath(a.links)), "short.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
    ok = sum(1 for o in out if o["short"])
    bad = [o["label"] for o in out if not o["short"]]
    why = {}
    for i in items:
        s, r = res[i["url"]]
        if not s:
            why[r] = why.get(r, 0) + 1
    line = f"shortened {ok}/{len(out)} -> {path}" + (f" | failed: {', '.join(bad)}" if bad else "")
    if why:
        line += " | reasons: " + ", ".join(f"{k}={v}" for k, v in sorted(why.items()))
    print(line)
    if "auth" in why:
        print("CODE=AUTH AroLinks ne token reject kiya (AROLINKS_TOKEN check karo); retry se fayda nahi")
    elif ok == 0 and why:
        print("CODE=" + ("RATE" if "rate" in why else "NETWORK" if "network" in why else "UNKNOWN"))
    if why:
        log_event("SHORTEN_" + "_".join(sorted(k.upper() for k in why)), f"ok={ok} total={len(out)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
