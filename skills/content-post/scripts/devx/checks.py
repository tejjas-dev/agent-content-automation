"""Final checks. Nothing is sent unless run() returns an empty list."""
from __future__ import annotations

import re

from . import config
from .caption import utf16
from .search import similarity

_LINK = re.compile(r"^📁 .+ : (https://arolinks\.com/\S+)$")


def run(spec, data: dict, short: list[str], captions: list[str], requested: str) -> list[str]:
    errs: list[str] = []
    if not data.get("title"):
        errs.append("title missing")
    elif similarity(requested, data["title"], spec.noise) < 0.6:
        errs.append("title does not match the requested drama")
    p = data.get("poster", "")
    if not (p.startswith("https://") or (config.allow_http() and p.startswith("http://"))):
        errs.append("poster missing")
    if not short:
        errs.append("no short links")
    if any(not s.startswith("https://arolinks.com/") for s in short):
        errs.append("invalid short link")
    if not captions:
        errs.append("no captions")
    heads, counts, used = [], [], []
    for i, c in enumerate(captions, 1):
        lines = c.split("\n")
        tag = f"post{i}"
        if not lines[0].startswith(spec.fields[0][1] + " : "):
            errs.append(f"{tag}: first line is not TITLE")
        if utf16(c) > config.CAPTION_LIMIT:
            errs.append(f"{tag}: too long ({utf16(c)} units)")
        if "[" in c or "]" in c:
            errs.append(f"{tag}: has [ or ]")
        if any(not u.startswith("https://arolinks.com/") for u in re.findall(r"https?://\S+", c)):
            errs.append(f"{tag}: has a non-short URL")
        links = [ln for ln in lines if ln.startswith("📁")]
        if not 1 <= len(links) <= config.MAX_LINKS_PER_POST:
            errs.append(f"{tag}: link count {len(links)} (need 1-{config.MAX_LINKS_PER_POST})")
        for ln in links:
            m = _LINK.match(ln)
            if m:
                used.append(m.group(1))
            else:
                errs.append(f"{tag}: bad link line")
        head = []
        for ln in lines:
            if ln.startswith("📁"):
                break
            if ln.strip():
                head.append(ln.strip())
        heads.append(tuple(head))
        counts.append(len(links))
    if len(set(heads)) > 1:
        errs.append("header differs between posts")
    if counts and max(counts) - min(counts) > 1:
        errs.append("links not balanced between posts")
    if sorted(used) != sorted(short):
        errs.append("captions do not match short links")
    return errs
