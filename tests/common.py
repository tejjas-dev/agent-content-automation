import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1] / "skills"
PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
       b"\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x9b\xa4\xb5"
       b"\x00\x00\x00\x00IEND\xaeB`\x82")


def load(skill, name):
    spec = importlib.util.spec_from_file_location(f"{skill}_{name}", ROOT / skill / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class S:                       # shared fake-server state
    calls, messages, fail_chats, reject_url, short_fail, short_hits = [], [], set(), False, set(), []
    short_body, short_status, timeout_chats = "", 200, set()      # short_body: text returned for a failing shorten call


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _s(self, code, body, ct="application/json"):
        b = body if isinstance(body, bytes) else body.encode()
        self.send_response(code); self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        u = urlsplit(self.path); q = parse_qs(u.query)
        if u.path == "/api":
            url = q.get("url", [""])[0]; S.short_hits.append(url)
            if url in S.short_fail or q.get("api", [""])[0] != "AROTOK":
                return self._s(S.short_status, S.short_body, "text/plain")
            return self._s(200, "https://arolinks.com/" + hashlib.sha1(url.encode()).hexdigest()[:7], "text/plain")
        if u.path == "/p.png":
            return self._s(200, PNG, "image/png")
        if u.path == "/page":
            return self._s(200, "<html><head><title>Hello Page</title></head><body>" + "x" * 300 + "</body></html>", "text/html")
        if u.path == "/blocked":
            return self._s(403, "<html><title>Just a moment...</title></html>", "text/html")
        if u.path == "/ok":
            return self._s(200, "<html>ok</html>", "text/html")
        if u.path == "/guard":
            return self._s(403, "<html><title>Just a moment...</title></html>", "text/html")
        if u.path == "/hop":                         # redirects to ANOTHER host name (localhost vs 127.0.0.1)
            self.send_response(302); self.send_header("Location", f"http://localhost:{self.server.server_address[1]}/ok")
            self.send_header("Content-Length", "0"); self.end_headers(); return
        if u.path == "/shell":
            return self._s(200, "<html><head><title>Home</title></head><body><h1>Search Results</h1><p>Loading...</p></body></html>" + " " * 300, "text/html")
        if u.path == "/slow-503":
            S.calls.append(("fetch", "503")); return self._s(503, "x", "text/html")
        self._s(404, "nope")

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path.endswith("/sendMessage"):
            S.messages.append(parse_qs(body.decode()))
            return self._s(200, json.dumps({"ok": True}))
        if self.headers.get("Content-Type", "").startswith("multipart"):
            chat = re.search(rb'name="chat_id"\r\n\r\n(.*?)\r\n', body).group(1).decode(); mode = "file"
        else:
            chat = parse_qs(body.decode())["chat_id"][0]; mode = "url"
        S.calls.append((chat, mode))
        if chat in S.timeout_chats:
            import time as _t; _t.sleep(3); return self._s(200, json.dumps({"ok": True}))
        if chat in S.fail_chats:
            return self._s(400, json.dumps({"ok": False, "description": "Bad Request: chat not found"}))
        if mode == "url" and S.reject_url:
            return self._s(400, json.dumps({"ok": False, "description": "wrong HTTP URL specified"}))
        self._s(200, json.dumps({"ok": True}))


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close()

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.data = self.tmp / "data"
        self.root = self.data / "drama"
        self.task = self.root / "work" / "t1"
        self.task.mkdir(parents=True)
        (self.root / "state").mkdir()
        env = {"DEVX_DATA_DIR": str(self.data), "AROLINKS_TOKEN": "AROTOK", "TELEGRAM_BOT_TOKEN": "TGTOK",
               "DRAMA_POST_CHANNEL_IDS": "-1,-2", "DEVX_AROLINKS_API": self.base + "/api",
               "DEVX_TELEGRAM_API": self.base, "DEVX_SEND_DELAY": "0", "DEVX_RETRY_CAP": "0", "DEVX_BACKOFF": "0"}
        # every DEVX_* / token variable is restored after the test, so one test's setting never leaks into the next
        keys = {*env, *(k for k in os.environ if k.startswith("DEVX_"))}
        self._old = {k: os.environ.get(k) for k in keys}
        for k in keys:
            os.environ.pop(k, None)
        os.environ.update(env)
        S.calls.clear(); S.messages.clear(); S.fail_chats.clear(); S.reject_url = False; S.short_fail.clear(); S.short_hits.clear()
        S.short_body, S.short_status = "", 200; S.timeout_chats.clear()

    def tearDown(self):
        for k, v in self._old.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def out(self, fn, *a):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = fn(list(a))
        return rc, buf.getvalue()

    def jwrite(self, name, obj, task=None):
        (task or self.task).joinpath(name).write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def caption(title="My Demon", links=(("480p Single Episode", "https://arolinks.com/aaa"), ("720p Zip File", "https://arolinks.com/bbb"))):
    head = f"📺 TITLE : {title}\n🎙 AUDIO : Hindi Dubbed\n📺 EPISODES : 16\n🎭 GENRE : Action, Comedy\n\n"
    return head + "".join(f"📁 {l} : {u}\n\n" for l, u in links)


DATA = {"title": "My Demon", "audio": "Hindi Dubbed", "episodes": "16", "genre": "Action, Comedy", "poster": "https://img.test/p.jpg"}
