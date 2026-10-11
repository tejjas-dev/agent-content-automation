#!/usr/bin/env python3
"""Shorten every link in ONE run (AroLinks). Order and label pairing are preserved by index.

  shorten.py links.json [--out short.json] [--workers 4]
  links.json : [{"label": "480p Single Episode", "url": "https://..."}, ...]
  short.json : same list + "short": "https://arolinks.com/..." or null (failed after one retry)
Env: AROLINKS_TOKEN (never printed).  Exit: 0 if at least one link was shortened, 1 if none, 2 on bad input.
"""
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

PREFIX = "https://arolinks.com/"
API = os.environ.get("DEVX_AROLINKS_API", "https://arolinks.com/api")


def shorten_one(url):
    q = urllib.parse.urlencode({"api": os.environ.get("AROLINKS_TOKEN", ""), "url": url, "format": "text"})
    try:
        req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=25) as r:
            out = r.read(2000).decode("utf-8", "replace").strip()
    except Exception:  # error text can contain the token URL: never surface it
        return None
    return out if out.startswith(PREFIX) else None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("links")
    ap.add_argument("--out")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args(argv)
    if not os.environ.get("AROLINKS_TOKEN"):
        print("ERROR: AROLINKS_TOKEN is not set")
        return 2
    try:
        items = json.load(open(a.links, encoding="utf-8"))
        assert isinstance(items, list) and all(i.get("url") and "label" in i for i in items)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: bad links file ({type(e).__name__})")
        return 2
    urls = list(dict.fromkeys(i["url"] for i in items))          # same URL -> one API call
    with ThreadPoolExecutor(max_workers=max(1, a.workers)) as ex:
        res = dict(zip(urls, ex.map(shorten_one, urls)))
    for u in [u for u, s in res.items() if not s]:               # one retry for failures
        res[u] = shorten_one(u)
    out = [{"label": i["label"], "url": i["url"], "short": res[i["url"]]} for i in items]
    path = a.out or os.path.join(os.path.dirname(os.path.abspath(a.links)), "short.json")
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    ok = sum(1 for o in out if o["short"])
    bad = [o["label"] for o in out if not o["short"]]
    print(f"shortened {ok}/{len(out)} -> {path}" + (f" | failed: {', '.join(bad)}" if bad else ""))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
