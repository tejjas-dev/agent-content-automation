#!/usr/bin/env python3
"""Deterministic pre-send check (zero tokens).  check.py --task DIR --title "requested title" [--type drama]
Prints PASS, or FAIL + one problem per line. Exit 0 / 1."""
import argparse
import glob
import json
import os
import re
import sys
from difflib import SequenceMatcher

HEADERS = {"drama": [("title", "📺 TITLE"), ("audio", "🎙 AUDIO"), ("episodes", "📺 EPISODES"), ("genre", "🎭 GENRE")]}
LIMIT, MAXLINKS = 950, 12
LINK = re.compile(r"^📁 (.+) : (https://arolinks\.com/\S+)$")


def units(s):
    return len(s.encode("utf-16-le")) // 2


def norm(s):
    return re.sub(r"\s+", " ", s.replace("[", "(").replace("]", ")")).strip()


def same_label(got, want):
    got = norm(got)
    return got == want or (got.endswith("…") and want.startswith(got[:-1]))


def squash(s):
    return re.sub(r"\W+", "", s.lower())


def jload(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def tload(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def run(task, title, typ="drama"):
    errs = []
    try:
        data = jload(os.path.join(task, "data.json"))
        short = jload(os.path.join(task, "short.json"))
    except Exception as e:  # noqa: BLE001
        return [f"cannot read data.json/short.json ({type(e).__name__})"]
    if not data.get("title"):
        errs.append("title missing in data.json")
    elif SequenceMatcher(None, squash(title), squash(data["title"])).ratio() < 0.6 and squash(title) not in squash(data["title"]):
        errs.append(f"title '{data['title']}' does not match requested '{title}'")
    poster = str(data.get("poster", ""))
    if not poster.startswith("https://"):
        errs.append("poster missing or not https")
    elif re.search(r"\s", poster) or not re.match(r"https://[^/\s]+\.[^/\s]+", poster):
        errs.append("poster URL is malformed (spaces must be %20, host needed)")
    want = {s["short"]: norm(s["label"]) for s in short if s.get("short")}
    if not want:
        errs.append("no shortened links")
    caps = sorted(glob.glob(os.path.join(task, "caption*.txt")), key=lambda f: int(re.findall(r"\d+", os.path.basename(f))[0]))
    if not caps:
        errs.append("no caption files")
    heads, counts, used = [], [], []
    for f in caps:
        t, tag = tload(f), os.path.basename(f)
        lines = t.split("\n")
        if units(t) > LIMIT:
            errs.append(f"{tag}: too long ({units(t)} units, max {LIMIT})")
        if "[" in t or "]" in t:
            errs.append(f"{tag}: contains [ or ]")
        if any(not u.startswith("https://arolinks.com/") for u in re.findall(r"https?://\S+", t)):
            errs.append(f"{tag}: has a non-short URL")
        links = [l for l in lines if l.startswith("📁")]
        if not 1 <= len(links) <= MAXLINKS:
            errs.append(f"{tag}: {len(links)} links (need 1-{MAXLINKS})")
        for l in links:
            m = LINK.match(l)
            if not m:
                errs.append(f"{tag}: bad link line: {l[:50]}")
            elif m.group(2) not in want:
                errs.append(f"{tag}: link {m.group(2)} is not in short.json")
            elif not same_label(m.group(1), want[m.group(2)]):
                errs.append(f"{tag}: label '{m.group(1)[:30]}' is attached to the wrong link {m.group(2)}")
            else:
                used.append(m.group(2))
        head = [l.strip() for l in lines[: next((i for i, l in enumerate(lines) if l.startswith("📁")), len(lines))] if l.strip()]
        heads.append(tuple(head))
        counts.append(len(links))
        exp = [f"{h} : {norm(str(data[k]))}" for k, h in HEADERS[typ] if data.get(k)]
        if head != exp:
            errs.append(f"{tag}: header does not match data.json (expected {len(exp)} lines)")
        if t.count("\n\n") < len(links) + 1:
            errs.append(f"{tag}: missing blank lines (need one after the header and after every link)")
    if len(set(heads)) > 1:
        errs.append("header differs between posts")
    if counts and max(counts) - min(counts) > 1:
        errs.append(f"links not balanced between posts {counts}")
    if sorted(used) != sorted(want):
        errs.append("captions do not use every shortened link exactly once")
    return errs


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--type", default="drama")
    a = ap.parse_args()
    e = run(a.task, a.title, a.type)
    print("PASS" if not e else "FAIL\n" + "\n".join("- " + x for x in e))
    sys.exit(1 if e else 0)
