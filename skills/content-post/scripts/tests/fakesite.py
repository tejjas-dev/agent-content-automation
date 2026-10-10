"""One local HTTP server that plays: a drama site, an image host, Telegram and AroLinks."""
from __future__ import annotations

import hashlib
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
       b"\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x9b\xa4\xb5"
       b"\x00\x00\x00\x00IEND\xaeB`\x82")

DRAMAS = {
    "my-unicorn-girl": dict(title="My Unicorn Girl", og="My Unicorn Girl (2024) Hindi Dubbed Download 720p - KatTest",
                            audio="Hindi", eps="16", genre="Romance / Fantasy / Comedy", n=14, kind="normal"),
    "moon-tales": dict(title="Moon Tales", og="Moon Tales Download - KatTest", audio="Hindi", eps="12",
                       genre="Fantasy", n=3, kind="normal"),
    "moon-tales-season-2": dict(title="Moon Tales Season 2", og="Moon Tales Season 2 Download - KatTest",
                                audio="Hindi", eps="10", genre="Fantasy", n=3, kind="normal"),
    "broken-layout": dict(title="Broken Layout", og="Broken Layout Download - KatTest", audio="Urdu",
                          eps="8", genre="Drama", n=3, kind="broken"),
    "bad-poster": dict(title="Bad Poster", og="Bad Poster Download - KatTest", audio="Hindi", eps="8",
                       genre="Drama", n=3, kind="badposter"),
}
DEFAULT_LISTING = [("Dream Garden", "dream-garden"), ("Old Story", "old-story")]


class State:
    def __init__(self):
        self.tg_calls: list[dict] = []
        self.fail_chats: set[str] = set()
        self.reject_url_mode = False
        self.short_fail: set[str] = set()
        self.home_param = "s"          # what the homepage search form claims (and which is ignored)


def detail_html(slug: str, d: dict) -> str:
    if d["kind"] == "broken":
        links = "".join(f'<a class="x" href="https://files.example.net/f/{i}?utm_source=k">Get {i}</a>'
                        for i in range(1, d["n"] + 1))
    else:
        links = "".join(f'<a href="https://drive.google.com/file/d/ID{i}?utm_source=kat&fbclid=zz">'
                        f'Episode {i} Download</a>' for i in range(1, d["n"] + 1))
    poster = "/img/bad.gif" if d["kind"] == "badposter" else "/img/unicorn.png"
    return f"""<html><head><title>{d['og']}</title>
<meta property="og:title" content="{d['og']}"><meta property="og:site_name" content="KatTest">
<meta property="og:image" content="{poster}"></head><body>
<header><nav><a href="/">Home</a><a href="/contact/">Contact</a></nav></header>
<article><h1 class="entry-title">{d['title']}</h1><img src="/img/logo.png">
<p><strong>Audio:</strong> {d['audio']}</p><p>Episodes: {d['eps']}</p>
<ul><li>Genre: {d['genre']}</li></ul><div class="downloads">{links}</div></article>
<footer><a href="https://t.me/kattest">Telegram</a> <a href="https://facebook.com/share?u=1">Share on Facebook</a></footer>
</body></html>"""


def cards(items) -> str:
    return "<div class='grid'>" + "".join(
        f"<article class='card'><a href='/drama/{s}/'><img src='/img/x.png' alt=''><h2>{t}</h2></a></article>"
        for t, s in items) + "</div>"


def make_server(state: State):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="text/html; charset=utf-8"):
            b = body if isinstance(body, bytes) else body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            u = urlsplit(self.path)
            q = parse_qs(u.query)
            if u.path == "/api":                                    # AroLinks
                url = q.get("url", [""])[0]
                if url in state.short_fail or q.get("api", [""])[0] != "AROTOK":
                    return self._send(200, "", "text/plain")
                return self._send(200, "https://arolinks.com/" + hashlib.sha1(url.encode()).hexdigest()[:7], "text/plain")
            if u.path == "/img/unicorn.png":
                return self._send(200, PNG, "image/png")
            if u.path == "/img/bad.gif":
                return self._send(200, b"GIF89a....", "image/gif")
            if u.path.startswith("/drama/"):
                slug = u.path.strip("/").split("/")[1]
                return self._send(200, detail_html(slug, DRAMAS[slug])) if slug in DRAMAS else self._send(404, "nope")
            if u.path == "/" and "q" in q:                          # real search param is q
                needle = unquote(q["q"][0]).lower()
                words = [w for w in needle.split() if w]
                hit = [(d["title"], s) for s, d in DRAMAS.items() if any(w in d["title"].lower() for w in words)]
                body = cards(hit) if hit else "<p>No results found</p>"
                return self._send(200, f"<html><body><main>{body}</main>{'x' * 200}</body></html>")
            if u.path == "/":                                       # homepage / ignored params
                form = f"<form action='/' method='get'><input type='search' name='{state.home_param}'></form>"
                return self._send(200, f"<html><body><header><nav><a href='/contact/'>Contact</a></nav>{form}</header>"
                                       f"<main>{cards(DEFAULT_LISTING)}</main>{'x' * 200}</body></html>")
            self._send(404, "not found")

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(n)
            m = re.match(r"/bot([^/]+)/(\w+)", self.path)
            if not m:
                return self._send(404, "{}", "application/json")
            method = m.group(2)
            if method in ("getMe",):
                return self._send(200, json.dumps({"ok": True}), "application/json")
            ctype = self.headers.get("Content-Type", "")
            if ctype.startswith("multipart"):
                chat = re.search(rb'name="chat_id"\r\n\r\n(.*?)\r\n', body).group(1).decode()
                cap = re.search(rb'name="caption"\r\n\r\n(.*?)\r\n--', body, re.S).group(1).decode()
                mode = "file"
            else:
                f = parse_qs(body.decode())
                chat, cap, mode = f["chat_id"][0], f.get("caption", [""])[0], "url"
            if method == "getChat":
                return self._send(200, json.dumps({"ok": chat not in state.fail_chats}), "application/json")
            state.tg_calls.append({"chat": chat, "caption": cap, "mode": mode})
            if chat in state.fail_chats:
                return self._send(400, json.dumps({"ok": False, "description": "Bad Request: chat not found"}), "application/json")
            if mode == "url" and state.reject_url_mode:
                return self._send(400, json.dumps({"ok": False, "description": "Bad Request: wrong file identifier/HTTP URL specified"}), "application/json")
            return self._send(200, json.dumps({"ok": True, "result": {}}), "application/json")

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
