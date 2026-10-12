#!/usr/bin/env python3
"""Compact extraction from a SAVED page, so the AI reads ~10 lines instead of the whole HTML (stdlib only, no network by default).

  extract.py PAGE.html --base URL [--write DIR] [--check-poster] [--source NAME]   drama page -> title, audio, episodes, genre, poster, links
  extract.py --cards PAGE.html --base URL [--out candidates.json] [--limit 20]     search page -> candidate drama pages (title, url, year, audio)

Prints  EXTRACT OK title=.. audio=.. episodes=.. genre=.. poster=.. links=N
        EXTRACT PARTIAL missing=title,poster,links ...   (the AI completes only the missing fields)
        EXTRACT FAIL js_shell | unreadable               (js_shell: fetch again with --tier dynamic)
--write DIR: extract.json (all alternatives) always; data.json once title+poster are known; links.json once a link is found
(formats of drama-scrape). Hints for a site (extra link hosts, hosts to skip) live in ../references/hints.json.
Exit 0 = OK, 1 = PARTIAL/FAIL."""
import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
VOID = {"br", "img", "meta", "link", "input", "hr", "source", "area", "base", "col", "embed", "param", "track", "wbr"}
FIELDS = {"title": ("title", "name", "drama name", "movie name", "series name"),
          "audio": ("audio", "language", "languages", "audio language", "audio languages", "dubbed in"),
          "episodes": ("episodes", "episode", "total episodes", "no of episodes"),
          "genre": ("genre", "genres")}
LABEL_LINE = re.compile(r"(?i)^(title|name|audio|languages?|audio languages?|episodes?|total episodes|genres?)\s*[:：]\s*(.+)$")
DL = re.compile(r"(?i)\b(\d{3,4}p|2160p|4k|zip|episodes?|ep\s?\d+|download|batch|single|bundle|mkv|mp4|av1|hevc|x26[45]|10\s?-?bit|season|part)\b")
DENY = ("facebook.com", "fb.com", "twitter.com", "x.com", "instagram.com", "youtube.com", "youtu.be", "t.me", "telegram.me", "telegram.org",
        "wa.me", "whatsapp.com", "pinterest.com", "play.google.com", "apps.apple.com", "tiktok.com", "linkedin.com", "reddit.com",
        "discord.gg", "discord.com", "imdb.com", "themoviedb.org", "wikipedia.org", "mydramalist.com", "google.com", "gravatar.com",
        "wordpress.org", "w.org", "gmpg.org")
TRACK = re.compile(r"(?i)^(utm_.*|fbclid|gclid|ref|mc_cid|mc_eid)$")
BAD_IMG = re.compile(r"(?i)logo|favicon|sprite|avatar|icon|emoji|banner|/ads?/|placeholder|default[-_.]|blank|pixel|spacer|\.svg|\.gif|^data:")
IMG_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
LANG_WORDS = r"hindi|english|korean|chinese|mandarin|japanese|thai|turkish|tamil|telugu|malayalam|kannada|bengali|urdu|punjabi|marathi|spanish|indonesian"


def clean(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title, self.meta, self.ld, self.imgs, self.anchors, self.chunks = "", {}, [], [], [], []
        self.stack, self.visible = [], []
        self._skip, self._in_title, self._ld, self._buf, self._a = 0, False, False, [], None

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "meta":
            k = (a.get("property") or a.get("name") or "").lower()
            if k and a.get("content"):
                self.meta.setdefault(k, a["content"].strip())
        if tag == "title":
            self._in_title = True
        if tag == "script":
            if "ld+json" in a.get("type", "").lower():
                self._ld, self._buf = True, []
            else:
                self._skip += 1
        elif tag in ("style", "noscript"):
            self._skip += 1
        if tag == "img":
            self.imgs.append(a)
            if self._a is not None:
                self._a["alt"] = self._a["alt"] or a.get("alt", "")
        if tag == "a" or a.get("data-href") or a.get("data-url") or a.get("data-link"):
            if tag == "a" and self._a is not None:
                self._close_a()
            href = a.get("href") if tag == "a" else ""
            href = href or a.get("data-href") or a.get("data-url") or a.get("data-link") or ""
            entry = {"href": href, "text": [], "alt": "", "title": a.get("title") or a.get("aria-label") or "", "tag": tag}
            if tag == "a":
                self._a = entry
            else:
                self.anchors.append({**entry, "text": clean(entry["title"])})
        if tag not in VOID:
            self.stack.append((tag, set(re.split(r"\s+", a.get("class", "").lower())) - {""}))

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag == "script":
            if self._ld:
                self._ld = False
                try:
                    self.ld.append(json.loads("".join(self._buf)))
                except ValueError:
                    pass
            elif self._skip:
                self._skip -= 1
        elif tag in ("style", "noscript") and self._skip:
            self._skip -= 1
        if tag == "a" and self._a is not None:
            self._close_a()
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def _close_a(self):
        e, self._a = self._a, None
        text = clean(" ".join(e["text"])) or clean(e["alt"]) or clean(e["title"])
        self.anchors.append({**e, "text": text})

    def handle_data(self, data):
        if self._ld:
            self._buf.append(data)
            return
        if self._skip:
            return
        if self._in_title:
            self.title += data
        t = clean(data)
        if not t:
            return
        self.visible.append(t)
        if self._a is not None:
            self._a["text"].append(t)
        tag, cls = self.stack[-1] if self.stack else ("", set())
        self.chunks.append((tag, cls, t))

    def close(self):
        super().close()
        if self._a is not None:
            self._close_a()


def parse(path):
    p = Page()
    p.feed(Path(path).read_text(encoding="utf-8", errors="replace"))
    p.close()
    return p


def host_of(u):
    return re.sub(r"^www\.", "", (urllib.parse.urlsplit(u).hostname or "").lower())


def norm_url(u, base):
    u = (u or "").strip()
    if not u or u.startswith(("#", "javascript:", "mailto:", "tel:", "data:")):
        return ""
    u = urllib.parse.urljoin(base, u)
    s = urllib.parse.urlsplit(u)
    if s.scheme not in ("http", "https") or not s.hostname:
        return ""
    q = [(k, v) for k, v in urllib.parse.parse_qsl(s.query, keep_blank_values=True) if not TRACK.match(k)]
    return urllib.parse.urlunsplit((s.scheme, s.netloc, s.path, urllib.parse.urlencode(q), ""))


def hints():
    try:
        h = json.loads((Path(__file__).absolute().parents[1] / "references" / "hints.json").read_text(encoding="utf-8"))
        return {"link_hosts": [x.lower() for x in h.get("link_hosts", [])], "skip_hosts": [x.lower() for x in h.get("skip_hosts", [])]}
    except (OSError, ValueError, AttributeError):
        return {"link_hosts": [], "skip_hosts": []}


def clean_title(s):
    """Pure drama name: drop (Chinese Drama), Hindi Dubbed, All Episodes, quality, [year], site name. Keep 'Season N'."""
    s = clean(s)
    junk = r"drama|dubbed|hindi|english|korean|chinese|japanese|thai|turkish|taiwanese|series|movie|webrip|web-dl|hdrip|bluray|\d{3,4}p|(?:19|20)\d{2}|download|episodes?"

    def paren(m):
        inner = m.group(1)
        if re.fullmatch(r"(?i)\s*season\s*\d+\s*", inner):
            return " " + clean(inner) + " "
        return " " if re.search(rf"(?i)\b(?:{junk})\b", inner) else m.group(0)

    s = re.sub(r"\(([^)]*)\)", paren, s)
    s = re.sub(r"\[([^\]]*)\]", paren, s)
    parts = re.split(r"\s+[|–—]\s+|\s+-\s+", s)
    if len(parts) > 1 and any(re.search(r"(?i)drama|download|watch|world|\.[a-z]{2,}\b|hindi|dubbed|episodes", p) for p in parts[1:]):
        s = parts[0]
    s = re.sub(r"(?i)\b(?:(?:hindi|english|korean|chinese|tamil|telugu)\s+)?dubbed\b", " ", s)
    s = re.sub(r"(?i)\ball episodes\b|\b(?:480p|720p|1080p|2160p|4k|web-?dl|webrip|hdrip|bluray|hdtv|x26[45]|hevc|10\s?bit)\b", " ", s)
    s = re.sub(r"(?i)\b(?:download|watch online|full (?:series|movie|drama))\b", " ", s)
    s = re.sub(r"(?i)\b(?:korean|chinese|thai|japanese|turkish|taiwanese)\s+drama\b", " ", s)
    return clean(s).strip(" -|:–—")


def info_pairs(page):
    """label -> value from label/value elements, dt/dd, th/td or 'Label: value' lines."""
    out, ch = {}, page.chunks

    def put(label, value):
        label = re.sub(r"[^a-z ]", "", label.lower()).strip()
        for field, names in FIELDS.items():
            if label in names and value and field not in out:
                out[field] = clean(value)

    for i, (tag, cls, text) in enumerate(ch):
        nxt = ch[i + 1] if i + 1 < len(ch) else None
        m = LABEL_LINE.match(text)
        if m:
            put(m.group(1), m.group(2))
        elif nxt and (any("label" in c for c in cls) or tag in ("dt", "th") or text.endswith(":")):
            if any("value" in c for c in nxt[1]) or nxt[0] in ("dd", "td") or text.endswith(":") or any("label" in c for c in cls):
                put(text.rstrip(":"), nxt[2])
    return out


def ld_nodes(page):
    def walk(x):
        if isinstance(x, dict):
            yield x
            for v in x.values():
                yield from walk(v)
        elif isinstance(x, list):
            for v in x:
                yield from walk(v)
    return [n for b in page.ld for n in walk(b)]


def poster_candidates(page, base):
    seen, out = set(), []

    def add(u):
        u = norm_url(u, base)
        if u.startswith("http://"):
            u = "https://" + u[7:]
        u = u.replace(" ", "%20").replace("(", "%28").replace(")", "%29")
        if u and u not in seen and not BAD_IMG.search(u):
            seen.add(u)
            out.append(u)

    def src(im):
        s = im.get("data-src") or im.get("data-lazy-src") or im.get("src") or ""
        return s or (im.get("srcset", "").split(",")[0].split(" ")[0] if im.get("srcset") else "")

    for k in ("og:image", "og:image:url", "twitter:image", "twitter:image:src"):
        add(page.meta.get(k))
    for im in page.imgs:
        if "image.tmdb.org" in src(im):
            add(src(im))
    for im in page.imgs:
        if re.search(r"(?i)poster|cover|featured|thumb", im.get("class", "") + " " + im.get("id", "")):
            add(src(im))
    for n in ld_nodes(page):
        img = n.get("image")
        for u in ([img] if isinstance(img, str) else [i for i in img if isinstance(i, str)] if isinstance(img, list) else
                  [img.get("url")] if isinstance(img, dict) else []):
            add(u)
    for im in page.imgs[:12]:
        add(src(im))
    return out[:6]


def poster_ok(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "image/*"})
        with urllib.request.urlopen(req, timeout=20) as r:
            ct, blob = r.headers.get_content_type(), r.read(5 * 1024 * 1024 + 1)
        return ct in IMG_TYPES and 100 < len(blob) <= 5 * 1024 * 1024
    except Exception:  # noqa: BLE001
        return False


def link_candidates(page, base):
    h, bh, seen, out = hints(), host_of(base), set(), []
    for a in page.anchors:
        u = norm_url(a["href"], base)
        if not u:
            continue
        host = host_of(u)
        if u.rstrip("/") == norm_url(base, base).rstrip("/") or any(host == d or host.endswith("." + d) for d in DENY + tuple(h["skip_hosts"])):
            continue
        label = clean(a["text"])
        path = urllib.parse.urlsplit(u).path
        allowed = any(host == d or host.endswith("." + d) for d in h["link_hosts"])
        if not (allowed or DL.search(label) or (host != bh and DL.search(path))):
            continue
        if u in seen:
            continue
        seen.add(u)
        out.append({"label": (label or host)[:120], "url": u})
    return out


def title_candidates(page, info):
    c = []
    if info.get("title"):
        c.append(info["title"])
    for n in ld_nodes(page):
        t = n.get("@type")
        t = t if isinstance(t, list) else [t]
        if any(x in ("Movie", "TVSeries", "TVSeason", "CreativeWork") for x in t) and isinstance(n.get("name"), str):
            c.append(n["name"])
    h1 = next((t for tag, _, t in page.chunks if tag == "h1"), "")
    c += [h1, page.meta.get("og:title", ""), page.title]
    out = []
    for t in c:
        t = clean_title(t)
        if t and t not in out:
            out.append(t)
    return out


def extract(path, base, source=""):
    p = parse(path)
    text = " ".join(p.visible)
    info = info_pairs(p)
    titles, posters, links = title_candidates(p, info), poster_candidates(p, base), link_candidates(p, base)
    d = {"title": titles[0] if titles else "", "audio": info.get("audio", ""), "episodes": info.get("episodes", ""),
         "genre": info.get("genre", ""), "poster": posters[0] if posters else "", "page_url": base, "source": source or host_of(base)}
    return {"data": d, "links": links, "title_alts": titles[1:4], "poster_alts": posters[1:4],
            "js_shell": len(text) < 300 and bool(re.search(r"(?i)loading|please wait|enable javascript", text))}


def cards(path, base, limit):
    p, bh, best = parse(path), host_of(base), {}
    for a in p.anchors:
        u = norm_url(a["href"], base)
        if not u or host_of(u) != bh:
            continue
        path_ = urllib.parse.urlsplit(u).path.strip("/")
        if not path_ or re.match(r"(?i)(?:wp-|(?:tag|category|genre|page|search|feed|author|contact|about|dmca|privacy|terms|login|register)(?:/|$))", path_):
            continue
        text = clean(a["text"])
        if len(text) < 2 or u.rstrip("/") == base.rstrip("/"):
            continue
        key = u.rstrip("/")
        if key not in best or len(text) > len(best[key]["raw"]):
            best[key] = {"raw": text, "url": u}
    out = []
    for v in best.values():
        year = re.search(r"\b((?:19|20)\d{2})\b", v["raw"])
        heard = re.sub(r"(?i)\b(?:korean|chinese|thai|japanese|turkish|taiwanese)\s+(?:drama|series|movie)s?\b", " ", v["raw"])   # origin, not audio
        aud = sorted(set(re.findall(rf"(?i)\b({LANG_WORDS})\b", heard)), key=str.lower)
        out.append({"title": clean_title(v["raw"]) or v["raw"], "url": v["url"], "year": year.group(1) if year else "",
                    "audio": ", ".join(x.title() for x in aud)})
    shell = len(" ".join(p.visible)) < 300 and bool(re.search(r"(?i)loading|please wait", " ".join(p.visible)))
    return out[:limit], shell


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("page", nargs="?")
    ap.add_argument("--cards")
    ap.add_argument("--base", required=True)
    ap.add_argument("--write")
    ap.add_argument("--out")
    ap.add_argument("--source", default="")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--check-poster", action="store_true")
    a = ap.parse_args(argv)
    try:
        if a.cards:
            found, shell = cards(a.cards, a.base, a.limit)
            if not found:
                print("EXTRACT FAIL js_shell (use --tier dynamic)" if shell else "EXTRACT FAIL no_candidates")
                return 1
            if a.out:
                Path(a.out).write_text(json.dumps(found, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"CANDIDATES {len(found)}" + (f" -> {a.out}" if a.out else ""))
            for i, c in enumerate(found, 1):
                print(f"{i} | {c['title']} | {c['year'] or '?'} | {c['audio'] or '?'} | {c['url']}")
            return 0
        if not a.page:
            ap.error("give PAGE.html or --cards PAGE.html")
        r = extract(a.page, a.base, a.source)
    except OSError:
        print("EXTRACT FAIL unreadable")
        return 1
    d, links = r["data"], r["links"]
    if a.check_poster and d["poster"] and not poster_ok(d["poster"]):
        alt = next((u for u in r["poster_alts"] if poster_ok(u)), "")
        d["poster"] = alt
    missing = [k for k, ok in (("title", d["title"]), ("poster", d["poster"]), ("links", links)) if not ok]
    if a.write:
        w = Path(a.write)
        (w / "extract.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        if d["title"] and d["poster"]:
            (w / "data.json").write_text(json.dumps({k: v for k, v in d.items() if v}, ensure_ascii=False), encoding="utf-8")
        if links:
            (w / "links.json").write_text(json.dumps(links, ensure_ascii=False), encoding="utf-8")
    if r["js_shell"] and missing:
        print("EXTRACT FAIL js_shell (page is only a JavaScript placeholder: fetch again with --tier dynamic)")
        return 1
    summ = f"title={d['title']!r} audio={d['audio']!r} episodes={d['episodes']!r} genre={d['genre']!r} poster={d['poster'] or '-'} links={len(links)}"
    print(("EXTRACT OK " if not missing else f"EXTRACT PARTIAL missing={','.join(missing)} ") + summ)
    if missing and r["title_alts"]:
        print("title alternatives: " + " | ".join(r["title_alts"]))
    return 0 if not missing else 1


if __name__ == "__main__":
    sys.exit(main())
