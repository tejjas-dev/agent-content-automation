"""Search-result candidates and title matching (fuzzy, season/year aware)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from urllib.parse import quote, urlsplit

from . import dom

ACCEPT = 0.82
DOUBT = 0.70
_SKIP_ANCESTORS = {"header", "nav", "footer", "aside"}
_NAV_TEXT = re.compile(r"^(home|log ?in|register|contact|about|privacy|dmca|menu|search|next|"
                       r"prev(ious)?|older|newer|page \d+|read more|more|categories|tags?)$", re.I)
_SKIP_PATH = re.compile(r"/(category|tag|page|author|feed|wp-content|wp-json)/|[?&](s|q|search)=", re.I)


@dataclass
class Cand:
    title: str
    url: str
    score: float = 0.0


def noise_re(noise) -> re.Pattern | None:
    words = sorted({w.lower() for w in noise if w}, key=len, reverse=True)
    return re.compile(r"\b(" + "|".join(re.escape(w) for w in words) + r")\b", re.I) if words else None


def normalize(s: str, noise=()) -> str:
    s = (s or "").lower()
    rx = noise_re(noise)
    if rx:
        s = rx.sub(" ", s)
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


def hints(s: str) -> tuple[int | None, str | None]:
    s = (s or "").lower()
    m = re.search(r"\b(?:season|s)\s*0?(\d{1,2})\b", s)
    y = re.search(r"\b(19\d\d|20\d\d)\b", s)
    return (int(m.group(1)) if m else None), (y.group(1) if y else None)


def similarity(query: str, cand: str, noise=()) -> float:
    nq, nc = normalize(query, noise), normalize(cand, noise)
    if not nq or not nc:
        return 0.0
    seq = SequenceMatcher(None, nq, nc).ratio()
    tq, tc = set(nq.split()), set(nc.split())
    contain = len(tq & tc) / len(tq)
    score = max(seq, 0.6 * contain + 0.4 * seq)
    if contain == 1 and len(tc - tq) <= 3:
        score = max(score, 0.9)
    qs, qy = hints(query)
    cs, cy = hints(cand)
    if qs is not None:
        if cs is not None and cs != qs:
            score *= 0.5
        elif cs is None and qs != 1:
            score *= 0.85
    if qy and cy and qy != cy:
        score *= 0.7
    return round(score, 4)


def relaxed_queries(query: str) -> list[str]:
    words = query.split()
    out = [query]
    if len(words) > 2:
        out.append(" ".join(words[:2]))
    if len(words) > 1:
        out.append(max(words, key=len))
    seen, res = set(), []
    for q in out:
        if q.lower() not in seen:
            seen.add(q.lower())
            res.append(q)
    return res


def search_url(origin: str, path_template: str, query: str) -> str:
    return origin.rstrip("/") + path_template.format(query=quote(query, safe=""))


def _best_text(a, card=None) -> str:
    t = dom.clean(a.get_text(" "))
    if len(t) >= 3:
        return t
    t = dom.clean(a.get("title"))
    if len(t) >= 3:
        return t
    img = a.find("img")
    if img is not None and len(dom.clean(img.get("alt"))) >= 3:
        return dom.clean(img.get("alt"))
    if card is not None:
        h = card.find(["h1", "h2", "h3", "h4"])
        if h is not None:
            return dom.clean(h.get_text(" "))
    return ""


def extract_candidates(soup, base_url: str, listing: dict) -> list[Cand]:
    site = dom.host(base_url)
    out: list[Cand] = []
    seen: set[str] = set()

    def add(a, title):
        url = dom.strip_tracking(dom.absolute(base_url, a.get("href")))
        if not url or url in seen or dom.host(url) != site:
            return
        p = urlsplit(url)
        if p.path in ("", "/") or _SKIP_PATH.search(url):
            return
        if not (3 <= len(title) <= 150) or _NAV_TEXT.match(title):
            return
        seen.add(url)
        out.append(Cand(title, url))

    cards = dom.select(soup, listing["card"]) if listing.get("card") else []
    if cards:
        for c in cards:
            links = dom.select(c, listing.get("link") or "a[href]")
            a = links[0] if links else (c if c.name == "a" else None)
            if a is None:
                continue
            tsel = dom.select(c, listing["title"]) if listing.get("title") else []
            title = dom.clean(tsel[0].get_text(" ")) if tsel else _best_text(a, c)
            add(a, title)
    else:
        for a in dom.select(soup, listing.get("link") or "a[href]"):
            if any(p.name in _SKIP_ANCESTORS for p in a.parents):
                continue
            add(a, _best_text(a, a.find_parent(["article", "li", "div"])))
    return out


def rank(query: str, cands: list[Cand], noise=()) -> list[Cand]:
    for c in cands:
        c.score = similarity(query, c.title, noise)
    return sorted(cands, key=lambda c: -c.score)


def pick(query: str, ranked: list[Cand]):
    """-> ("accept", cand) | ("ambiguous", [cands]) | ("none", best_score)"""
    if not ranked or ranked[0].score < DOUBT:
        return "none", (ranked[0].score if ranked else 0.0)
    top = ranked[0]
    close = [c for c in ranked[1:] if c.score >= ACCEPT and top.score - c.score < 0.06]
    if top.score >= ACCEPT:
        # query names no season but another strong candidate is a different season/year: ask,
        # because posting the wrong season to public channels is worse than one question
        if hints(query)[0] is None:
            th = hints(top.title)
            close += [c for c in ranked[1:] if c.score >= 0.85 and c not in close
                      and c.url != top.url and hints(c.title) != th]
        return ("ambiguous", [top] + close[:2]) if close else ("accept", top)
    return "ambiguous", ranked[:3]


def is_default_listing(cands: list[Cand], home_urls: set[str]) -> bool:
    """A search param the site silently ignores returns the homepage's default cards."""
    if not cands or not home_urls:
        return False
    return sum(c.url in home_urls for c in cands) / len(cands) >= 0.8


def discover_params(soup, base_url: str) -> list[tuple[str, str]]:
    """(action_url, input_name) pairs from search forms, then common probes."""
    found: list[tuple[str, str]] = []
    for f in soup.find_all("form"):
        inp = f.find("input", attrs={"type": re.compile("^(search|text)$", re.I)}) or \
              f.find("input", attrs={"name": re.compile("^(s|q|search|query|keyword)", re.I)})
        if inp is not None and inp.get("name"):
            action = dom.absolute(base_url, f.get("action") or base_url) or base_url
            found.append((action, inp["name"]))
    for name in ("s", "q", "search", "search_query"):
        found.append((base_url, name))
    seen, out = set(), []
    for pair in found:
        if pair not in seen:
            seen.add(pair)
            out.append(pair)
    return out
