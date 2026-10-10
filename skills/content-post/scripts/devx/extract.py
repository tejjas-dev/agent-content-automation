"""Detail-page extraction (title, fields, poster candidates, links) + repair digest."""
from __future__ import annotations

import re

from . import dom
from .search import noise_re

_FILE_HOSTS = ("drive.google.com", "mega.nz", "mediafire.com", "pixeldrain.com", "gofile.io",
               "terabox.com", "1fichier.com", "krakenfiles.com", "dropbox.com", "send.cm",
               "buzzheavier.com", "katfile.com", "ddownload.com", "workupload.com")
_BAD_IMG = re.compile(r"logo|icon|avatar|favicon|sprite|banner|placeholder|blank|pixel|emoji", re.I)


def clean_title(raw: str, noise, site_names=()) -> str:
    t = dom.clean(raw)
    rx = noise_re(noise)
    if rx:
        t = rx.sub(" ", t)
    for sn in site_names:
        if sn:
            t = re.sub(r"[\s\-–—|:]*" + re.escape(sn) + r"\s*$", "", t, flags=re.I)
    t = re.split(r"\s+[|–—]\s+", t)[0]
    t = re.sub(r"\(\s*\)|\[\s*\]", " ", t)
    t = re.sub(r"[\s\-–—|:,]+$", "", dom.clean(t))
    t = re.sub(r"^[\s\-–—|:,]+", "", t)
    return dom.clean(t)


def _site_names(soup, url: str) -> list[str]:
    names = [dom.meta(soup, "og:site_name")]
    h = dom.host(url).split(".")
    names.append(h[-2] if len(h) >= 2 else h[0])
    return [n for n in names if n]


def pick_title(soup, url: str, spec, rule: dict, extra_noise) -> str:
    noise = list(spec.noise) + list(extra_noise)
    sites = _site_names(soup, url)
    cands = [dom.meta(soup, m) for m in rule.get("meta", [])]
    for sel in rule.get("css", []):
        el = (dom.select(soup, sel) or [None])[0]
        if el is not None:
            cands.append(el.get_text(" "))
    if soup.title is not None:
        cands.append(soup.title.get_text(" "))
    for c in cands:
        t = clean_title(c, noise, sites)
        if len(t) >= 2:
            return t
    return ""


def _main_text_lines(soup) -> list[str]:
    root = None
    for sel in ("article", "main", ".entry-content", ".post-content", "#content", ".content"):
        root = (dom.select(soup, sel) or [None])[0]
        if root is not None:
            break
    root = root or soup.body or soup
    return [dom.clean(x) for x in root.get_text("\n").split("\n") if dom.clean(x)]


def _from_lines(lines: list[str], label: str) -> str:
    rx = re.compile(rf"^[\W_]*(?:{label})\s*[:\-–—|]\s*(.*)$", re.I)
    for i, ln in enumerate(lines):
        m = rx.match(ln)
        if not m:
            continue
        val = dom.clean(m.group(1))
        if not val and i + 1 < len(lines):
            val = lines[i + 1]
        if val and len(val) <= 120:
            return val.strip(" .;,")
    return ""


def pick_field(soup, lines, key: str, rule: dict, default_label: str) -> str:
    for sel in rule.get("css", []):
        el = (dom.select(soup, sel) or [None])[0]
        if el is not None and dom.clean(el.get_text(" ")):
            return dom.clean(el.get_text(" "))[:120]
    label = rule.get("label") or default_label
    val = _from_lines(lines, label) if label else ""
    if val and key == "genre":
        parts = [p.strip() for p in re.split(r"\s*[/|;,]\s*", val) if p.strip()]
        val = ", ".join(dict.fromkeys(parts))
    return val


def poster_candidates(soup, url: str, rule: dict) -> list[str]:
    out: list[str] = []

    def add(u):
        u = dom.absolute(url, u)
        if u and u not in out and not _BAD_IMG.search(u.rsplit("/", 1)[-1]):
            out.append(u)

    for m in rule.get("meta", []):
        add(dom.meta(soup, m))
    sels = list(rule.get("css", [])) + ["article img", ".entry-content img", "main img", "img"]
    for sel in sels:
        for img in dom.select(soup, sel)[:8]:
            src = (img.get("data-src") or img.get("data-lazy-src") or img.get("data-original")
                   or img.get("src") or (img.get("srcset") or "").split(" ")[0])
            add(src)
        if len(out) >= 6:
            break
    return out[:8]


def _label_for(a, href: str) -> str:
    t = dom.clean(a.get_text(" ")) or dom.clean(a.get("title")) or dom.clean(a.get("aria-label"))
    t = re.sub(r"[\[\]]", lambda m: "(" if m.group() == "[" else ")", t)
    return t[:60] if t else dom.host(href)


def collect_links(soup, url: str, rule: dict) -> list[tuple[str, str]]:
    inc = re.compile(rule["text_include"]) if rule.get("text_include") else None
    exc = re.compile(rule["text_exclude"]) if rule.get("text_exclude") else None
    bad_hosts = tuple(h.lower() for h in rule.get("host_exclude", []))
    here = dom.strip_tracking(url).rstrip("/")
    roots = dom.select(soup, rule["container"]) if rule.get("container") else [soup]
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    nodes = []
    for r in roots or [soup]:
        for sel in rule.get("css", ["a[href]"]):
            nodes += dom.select(r, sel)
        nodes += dom.select(r, "[data-href],[data-url],[data-link]")
    for a in nodes:
        raw = a.get("href") or a.get("data-href") or a.get("data-url") or a.get("data-link")
        href = dom.strip_tracking(dom.absolute(url, raw))
        if not href or href.rstrip("/") == here or href in seen:
            continue
        h = dom.host(href)
        if any(h == b or h.endswith("." + b) for b in bad_hosts):
            continue
        label = _label_for(a, href)
        if exc and exc.search(label):
            continue
        file_host = any(h == f or h.endswith("." + f) for f in _FILE_HOSTS)
        if inc and not (inc.search(label) or file_host):
            continue
        seen.add(href)
        out.append((label, href))
    return out


def extract(html: str, url: str, prof: dict, spec) -> dict:
    soup = dom.parse(html)
    D = prof["detail"]
    for t in soup(["script", "style", "noscript", "template"]):
        t.decompose()
    lines = _main_text_lines(soup)
    data = {"page_url": url,
            "title": pick_title(soup, url, spec, D["title"], prof.get("title_noise", []))}
    for key, _hdr in spec.fields:
        if key == "title":
            continue
        data[key] = pick_field(soup, lines, key, D["fields"].get(key, {}), spec.labels.get(key, ""))
    data["poster_candidates"] = poster_candidates(soup, url, D["poster"])
    data["links"] = collect_links(soup, url, D["links"])
    return data


def make_digest(html: str, url: str, max_chars: int = 6500) -> str:
    """Compact, deterministic view of a page for an AI to write selectors from."""
    soup = dom.parse(html)
    out = [f"URL: {url}", f"<title>: {dom.clean(soup.title.get_text(' ')) if soup.title else ''}"]
    for m in soup.find_all("meta"):
        k = m.get("property") or m.get("name") or ""
        if k.startswith(("og:", "twitter:")) or k == "description":
            out.append(f"meta {k} = {dom.clean(m.get('content'))[:160]}")
    for t in soup(["script", "style", "noscript", "svg", "iframe", "link", "template"]):
        t.decompose()

    def path(el) -> str:
        parts = []
        for p in [el] + list(el.parents)[:3]:
            if getattr(p, "name", None) in (None, "[document]", "html", "body"):
                break
            cls = ".".join((p.get("class") or [])[:2])
            parts.append(p.name + (f"#{p['id']}" if p.get("id") else "") + (f".{cls}" if cls else ""))
        return " < ".join(parts)

    out.append("--- headings")
    for h in soup.find_all(["h1", "h2", "h3"])[:12]:
        out.append(f"{path(h)}: {dom.clean(h.get_text(' '))[:100]}")
    out.append("--- info lines (label: value)")
    n = 0
    for ln in (dom.clean(x) for x in soup.get_text("\n").split("\n")):
        if 3 < len(ln) < 140 and re.match(r"^[\W_]*[A-Za-z ]{3,22}\s*[:\-–]\s*\S", ln):
            out.append(ln)
            n += 1
            if n >= 25:
                break
    out.append("--- images")
    for img in soup.find_all("img")[:15]:
        src = img.get("data-src") or img.get("src") or ""
        out.append(f"{path(img)} src={src[:140]} alt={dom.clean(img.get('alt'))[:50]}")
    out.append("--- anchors")
    for a in soup.find_all("a", href=True)[:110]:
        out.append(f"{path(a)} href={a['href'][:140]} text={dom.clean(a.get_text(' '))[:50]!r}")
    s = "\n".join(out)
    return s[:max_chars]
