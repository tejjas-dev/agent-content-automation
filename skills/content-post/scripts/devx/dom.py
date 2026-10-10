"""HTML helpers on top of BeautifulSoup (+lxml when present)."""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

_TRACK = re.compile(r"^(utm_|fbclid$|gclid$|mc_|igshid$|ref$|ref_)", re.I)


def parse(html: str) -> BeautifulSoup:
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")


def select(root, css: str) -> list:
    try:
        return root.select(css)
    except Exception:
        return []


def clean(s: object) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def meta(soup, *names: str) -> str:
    for n in names:
        el = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n})
        if el is not None and clean(el.get("content")):
            return clean(el.get("content"))
    return ""


def host(url: str) -> str:
    h = urlsplit(url).netloc.lower()
    return h[4:] if h.startswith("www.") else h


def strip_tracking(url: str) -> str:
    p = urlsplit(url)
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not _TRACK.match(k)]
    return urlunsplit((p.scheme, p.netloc, p.path, urlencode(q), ""))


def absolute(base: str, href: str | None) -> str:
    href = (href or "").strip()
    if not href or href.startswith(("#", "javascript:", "mailto:", "tel:", "data:")):
        return ""
    u = urljoin(base, href)
    return u if urlsplit(u).scheme in ("http", "https") else ""
