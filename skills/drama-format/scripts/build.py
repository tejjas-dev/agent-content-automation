#!/usr/bin/env python3
"""Build the locked caption(s).   build.py --task DIR [--type drama]
Reads data.json + short.json, writes caption1.txt, caption2.txt, ... (fewest posts, balanced, <= 950 UTF-16 units,
<= 12 links each). Entries whose short link failed (null) lose their tag. Exit: 0 ok, 3 no links, 4 header too long."""
import argparse
import json
import math
import os
import re
import sys

HEADERS = {"drama": [("title", "📺 TITLE"), ("audio", "🎙 AUDIO"), ("episodes", "📺 EPISODES"), ("genre", "🎭 GENRE")]}
LIMIT, MAXLINKS = 950, 12


def units(s):
    return len(s.encode("utf-16-le")) // 2


def tidy(s):
    return re.sub(r"\s+", " ", str(s).replace("[", "(").replace("]", ")")).strip()


def sizes(total, n):
    q, r = divmod(total, n)                      # 13 -> 7+6, 25 -> 9+8+8
    return [q + 1] * r + [q] * (n - r)


def build(data, items, typ="drama"):
    head = "\n".join(f"{h} : {tidy(data[k])}" for k, h in HEADERS[typ] if data.get(k))
    for cap in (None, 40, 28, 18):               # trim long labels only when needed
        rows = [(l if cap is None or len(l) <= cap else l[: cap - 1].rstrip() + "…", s) for l, s in items]
        for n in range(max(1, math.ceil(len(rows) / MAXLINKS)), len(rows) + 1):
            out, i = [], 0
            for size in sizes(len(rows), n):
                out.append(head + "\n\n" + "".join(f"📁 {l} : {s}\n\n" for l, s in rows[i:i + size]))
                i += size
            if all(units(c) <= LIMIT for c in out):
                return out
    return None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True)
    ap.add_argument("--type", default="drama")
    a = ap.parse_args(argv)
    try:
        with open(os.path.join(a.task, "data.json"), encoding="utf-8") as fh:
            data = json.load(fh)
        with open(os.path.join(a.task, "short.json"), encoding="utf-8") as fh:
            short = json.load(fh)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR cannot read data.json/short.json ({type(e).__name__})")
        return 2
    items = [(tidy(s["label"]), s["short"]) for s in short if s.get("short")]
    if not items:
        print("NO_LINKS no shortened link left")
        return 3
    caps = build(data, items, a.type)
    if caps is None:
        print("HEADER_TOO_LONG header bahut lamba hai")
        return 4
    for old in os.listdir(a.task):
        if re.fullmatch(r"caption\d+\.txt", old):
            os.remove(os.path.join(a.task, old))
    for i, c in enumerate(caps, 1):
        with open(os.path.join(a.task, f"caption{i}.txt"), "w", encoding="utf-8") as fh:
            fh.write(c)
    dropped = len(short) - len(items)
    print(f"built {len(caps)} post(s), {len(items)} link(s)" + (f", dropped {dropped} unshortened" if dropped else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
