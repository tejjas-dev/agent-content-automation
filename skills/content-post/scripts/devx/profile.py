"""Source profiles: JSON data describing HOW to read one site. Code never hardcodes sites.

Shipped profiles live in sources/<type>/*.json (from GitHub). AI repairs and new sources are
saved as overrides in <data>/overrides/<type>/<id>.json, outside the skill folder, so
`hermes skills update` can never wipe them. A failing override rolls back to the shipped one.
"""
from __future__ import annotations

import copy
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

from . import config

TIERS = ("http", "dynamic", "stealth")

DEFAULT_INCLUDE = (r"(?i)download|episode|\bep\.?\s*\d+|\b(?:480|720|1080|2160)p?\b|g-?drive|"
                   r"mirror|mega|pixeldrain|gofile|terabox|mediafire|server")
DEFAULT_EXCLUDE = (r"(?i)^(home|log ?in|register|sign ?up|contact|about|privacy|dmca|disclaimer|"
                   r"telegram|join|facebook|twitter|instagram|whatsapp|youtube|share|comments?|"
                   r"reply|next|prev|previous|older|newer|categor\w*|tags?|how to download|request)\b")
DEFAULT_HOST_EXCLUDE = [
    "facebook.com", "fb.com", "twitter.com", "x.com", "instagram.com", "youtube.com", "youtu.be",
    "t.me", "telegram.me", "telegram.org", "whatsapp.com", "wa.me", "pinterest.com",
    "play.google.com", "apps.apple.com", "linkedin.com", "tiktok.com", "reddit.com", "disqus.com",
]

DEFAULTS: dict = {
    "schema": 1,
    "order": 100,
    "entry_urls": [],
    "fetch": {"search_tier": "http", "detail_tier": "http", "wait_selector": ""},
    "search": {"mode": "template", "path": "/?q={query}"},
    "listing": {"card": "", "link": "a[href]", "title": ""},
    "detail": {
        "title": {"meta": ["og:title", "twitter:title"], "css": ["h1"]},
        "poster": {"meta": ["og:image", "twitter:image"], "css": []},
        "fields": {},
        "links": {"container": "", "css": ["a[href]"], "text_include": DEFAULT_INCLUDE,
                  "text_exclude": DEFAULT_EXCLUDE, "host_exclude": DEFAULT_HOST_EXCLUDE},
    },
    "title_noise": [],
}

_STR_LIST = [str]
SCHEMA: dict = {
    "schema": int, "id": str, "type": str, "order": int, "entry_urls": _STR_LIST,
    "fetch": {"search_tier": TIERS, "detail_tier": TIERS, "wait_selector": str},
    "search": {"mode": ("template", "auto"), "path": str},
    "listing": {"card": str, "link": str, "title": str},
    "detail": {
        "title": {"meta": _STR_LIST, "css": _STR_LIST},
        "poster": {"meta": _STR_LIST, "css": _STR_LIST},
        "fields": {"*": {"css": _STR_LIST, "label": str}},
        "links": {"container": str, "css": _STR_LIST, "text_include": str,
                  "text_exclude": str, "host_exclude": _STR_LIST},
    },
    "title_noise": _STR_LIST,
}


def _check(node, schema, path: str, errs: list) -> None:
    if isinstance(schema, dict):
        if not isinstance(node, dict):
            errs.append(f"{path}: must be an object")
            return
        for k, v in node.items():
            sub = schema.get(k, schema.get("*"))
            if sub is None:
                errs.append(f"{path}.{k}: unknown key")
            else:
                _check(v, sub, f"{path}.{k}", errs)
    elif isinstance(schema, list):
        if not isinstance(node, list) or not all(isinstance(x, schema[0]) for x in node):
            errs.append(f"{path}: must be a list of {schema[0].__name__}")
    elif isinstance(schema, tuple):
        if node not in schema:
            errs.append(f"{path}: must be one of {list(schema)}")
    elif schema is int:
        if not isinstance(node, int) or isinstance(node, bool):
            errs.append(f"{path}: must be an integer")
    elif schema is str:
        if not isinstance(node, str):
            errs.append(f"{path}: must be a string")


def _css_and_regex(p: dict, errs: list) -> None:
    import soupsieve as sv

    def css(sel, where):
        if sel:
            try:
                sv.compile(sel)
            except Exception as e:  # noqa: BLE001
                errs.append(f"{where}: bad CSS selector {sel!r} ({str(e)[:60]})")

    def rx(pat, where):
        if pat:
            try:
                re.compile(pat)
            except re.error as e:
                errs.append(f"{where}: bad regex ({e})")

    lst = p.get("listing", {})
    for k in ("card", "link", "title"):
        css(lst.get(k, ""), f"listing.{k}")
    d = p.get("detail", {})
    for sect in ("title", "poster"):
        for s in d.get(sect, {}).get("css", []):
            css(s, f"detail.{sect}.css")
    for key, f in d.get("fields", {}).items():
        for s in f.get("css", []):
            css(s, f"detail.fields.{key}.css")
        rx(f.get("label", ""), f"detail.fields.{key}.label")
    ln = d.get("links", {})
    css(ln.get("container", ""), "detail.links.container")
    for s in ln.get("css", []):
        css(s, "detail.links.css")
    rx(ln.get("text_include", ""), "detail.links.text_include")
    rx(ln.get("text_exclude", ""), "detail.links.text_exclude")
    css(p.get("fetch", {}).get("wait_selector", ""), "fetch.wait_selector")


def validate(p: dict) -> tuple[bool, list[str]]:
    errs: list[str] = []
    if not isinstance(p, dict):
        return False, ["profile must be a JSON object"]
    _check(p, SCHEMA, "profile", errs)
    if not re.fullmatch(r"[a-z0-9_-]{1,32}", str(p.get("id", ""))):
        errs.append("id: required, lowercase letters/digits/-/_ (max 32)")
    urls = p.get("entry_urls")
    if not urls:
        errs.append("entry_urls: at least one URL required")
    for u in urls or []:
        ok = u.startswith("https://") or (config.allow_http() and u.startswith("http://"))
        if not ok:
            errs.append(f"entry_urls: {u!r} must start with https://")
    s = p.get("search", {})
    if s.get("mode", "template") == "template" and "{query}" not in s.get("path", "/?q={query}"):
        errs.append("search.path: must contain {query}")
    if not errs:
        _css_and_regex(p, errs)
    return (not errs), errs[:12]


def merge(p: dict) -> dict:
    """Overlay profile p on DEFAULTS (dicts merge, lists/scalars replace)."""
    def rec(base, over):
        out = copy.deepcopy(base)
        for k, v in over.items():
            if isinstance(v, dict) and isinstance(out.get(k), dict) and k != "fields":
                out[k] = rec(out[k], v)
            else:
                out[k] = copy.deepcopy(v)
        return out
    return rec(DEFAULTS, p)


@dataclass
class Prof:
    id: str
    data: dict
    origin: str                 # shipped | override | custom | candidate
    shipped: dict | None = None  # merged shipped version, for rollback


def _load(f: Path) -> dict | None:
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def override_dir(type_name: str) -> Path:
    return config.sub(f"overrides/{type_name}")


def effective_profiles(type_name: str) -> list[Prof]:
    shipped: dict[str, dict] = {}
    for f in sorted((config.sources_dir() / type_name).glob("*.json")):
        if f.name.startswith("_"):
            continue
        d = _load(f)
        if d and validate(d)[0]:
            shipped[d["id"]] = d
    over: dict[str, dict] = {}
    for f in sorted(override_dir(type_name).glob("*.json")):
        d = _load(f)
        if d and validate(d)[0] and d.get("id") == f.stem:
            over[d["id"]] = d
        else:
            mark_bad(type_name, f.stem)
    out: list[Prof] = []
    for pid in set(shipped) | set(over):
        if pid in over:
            out.append(Prof(pid, merge(over[pid]), "override" if pid in shipped else "custom",
                            merge(shipped[pid]) if pid in shipped else None))
        else:
            out.append(Prof(pid, merge(shipped[pid]), "shipped"))
    return sorted(out, key=lambda p: (p.data.get("order", 100), p.id))


def mark_bad(type_name: str, pid: str) -> None:
    f = override_dir(type_name) / f"{pid}.json"
    if f.exists():
        hist = config.sub(f"overrides/{type_name}/.history")
        f.rename(hist / f"{pid}.bad.{int(time.time())}.json")


def save_override(type_name: str, p: dict) -> Path:
    f = override_dir(type_name) / f"{p['id']}.json"
    if f.exists():
        hist = config.sub(f"overrides/{type_name}/.history")
        f.rename(hist / f"{p['id']}.{int(time.time())}.json")
        for old in sorted(hist.glob(f"{p['id']}.*.json"))[:-5]:
            old.unlink(missing_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(p, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(f)
    return f
