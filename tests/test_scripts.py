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
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1] / "skills"
PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
       b"\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x9b\xa4\xb5"
       b"\x00\x00\x00\x00IEND\xaeB`\x82")


def load(skill, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / skill / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class S:                       # shared fake-server state
    calls, fail_chats, reject_url, short_fail, short_hits = [], set(), False, set(), []


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
                return self._s(200, "", "text/plain")
            return self._s(200, "https://arolinks.com/" + hashlib.sha1(url.encode()).hexdigest()[:7], "text/plain")
        if u.path == "/p.png":
            return self._s(200, PNG, "image/png")
        self._s(404, "nope")

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.headers.get("Content-Type", "").startswith("multipart"):
            chat = re.search(rb'name="chat_id"\r\n\r\n(.*?)\r\n', body).group(1).decode(); mode = "file"
        else:
            chat = parse_qs(body.decode())["chat_id"][0]; mode = "url"
        S.calls.append((chat, mode))
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
        cls.srv.shutdown()

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.task = self.tmp / "data" / "work" / "t1"
        self.task.mkdir(parents=True)
        env = {"DEVX_DATA_DIR": str(self.tmp / "data"), "AROLINKS_TOKEN": "AROTOK", "TELEGRAM_BOT_TOKEN": "TGTOK",
               "DRAMA_POST_CHANNEL_IDS": "-1,-2", "DEVX_AROLINKS_API": self.base + "/api",
               "DEVX_TELEGRAM_API": self.base, "DEVX_SEND_DELAY": "0", "DEVX_RETRY_CAP": "0"}
        self._old = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        S.calls.clear(); S.fail_chats.clear(); S.reject_url = False; S.short_fail.clear(); S.short_hits.clear()

    def tearDown(self):
        for k, v in self._old.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def out(self, fn, *a):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = fn(list(a))
        return rc, buf.getvalue()

    def jwrite(self, name, obj):
        (self.task / name).write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


class TestShorten(Base):
    def test_order_pairing_failure_and_dedupe(self):
        sh = load("link-short", "shorten")
        items = [{"label": f"L{i}", "url": f"https://x.test/{i}"} for i in range(6)] + [{"label": "dup", "url": "https://x.test/0"}]
        S.short_fail.add("https://x.test/3")
        self.jwrite("links.json", items)
        rc, out = self.out(sh.main, str(self.task / "links.json"))
        res = json.loads((self.task / "short.json").read_text())
        self.assertEqual(rc, 0)
        self.assertEqual([r["label"] for r in res], [i["label"] for i in items])          # order kept
        self.assertEqual(res[0]["short"], res[6]["short"])                                # same URL, same short
        self.assertIsNone(res[3]["short"])
        self.assertIn("shortened 6/7", out); self.assertIn("failed: L3", out)
        self.assertEqual(S.short_hits.count("https://x.test/0"), 1)                        # one call per unique URL
        self.assertNotIn("AROTOK", out)

    def test_all_fail_and_no_token(self):
        sh = load("link-short", "shorten")
        S.short_fail.add("https://x.test/1")
        self.jwrite("links.json", [{"label": "a", "url": "https://x.test/1"}])
        self.assertEqual(self.out(sh.main, str(self.task / "links.json"))[0], 1)
        os.environ.pop("AROLINKS_TOKEN")
        self.assertEqual(self.out(sh.main, str(self.task / "links.json"))[0], 2)


def caption(title="My Demon", links=(("480p Single Episode", "https://arolinks.com/aaa"), ("720p Zip File", "https://arolinks.com/bbb"))):
    head = f"📺 TITLE : {title}\n🎙 AUDIO : Hindi Dubbed\n📺 EPISODES : 16\n🎭 GENRE : Action, Comedy\n\n"
    return head + "".join(f"📁 {l} : {u}\n\n" for l, u in links)


class TestCheck(Base):
    def setup_task(self, cap=None, short=None, data=None):
        self.jwrite("data.json", data or {"title": "My Demon", "audio": "Hindi Dubbed", "episodes": "16", "genre": "Action, Comedy", "poster": "https://img.test/p.jpg"})
        self.jwrite("short.json", short or [{"label": "480p Single Episode", "url": "u1", "short": "https://arolinks.com/aaa"},
                                           {"label": "720p Zip File", "url": "u2", "short": "https://arolinks.com/bbb"},
                                           {"label": "dead", "url": "u3", "short": None}])
        (self.task / "caption1.txt").write_text(cap or caption(), encoding="utf-8")

    def run_check(self, title="my demon drama"):
        return load("drama-verify", "check").run(str(self.task), title)

    def test_pass(self):
        self.setup_task()
        self.assertEqual(self.run_check(), [])

    def test_wrong_label_link_pairing_is_caught(self):
        self.setup_task(cap=caption(links=(("480p Single Episode", "https://arolinks.com/bbb"), ("720p Zip File", "https://arolinks.com/aaa"))))
        self.assertTrue(any("wrong link" in e for e in self.run_check()))

    def test_other_failures(self):
        self.setup_task(cap=caption().replace("Hindi Dubbed", "English"))
        self.assertTrue(any("header does not match" in e for e in self.run_check()))
        self.setup_task(cap=caption(links=(("a", "https://evil.com/x"), ("b", "https://arolinks.com/bbb"))))
        self.assertTrue(any("non-short URL" in e for e in self.run_check()))
        self.setup_task(cap=caption().replace("\n\n📁", "\n📁", 1))
        self.assertTrue(any("blank" in e for e in self.run_check()))
        self.setup_task(cap=caption(links=(("480p Single Episode", "https://arolinks.com/aaa"),)))
        self.assertTrue(any("exactly once" in e for e in self.run_check()))
        self.setup_task(cap=caption(title="My Demon") + "x" * 1000)
        self.assertTrue(any("too long" in e for e in self.run_check()))
        self.setup_task(cap=caption().replace("[", "").replace("480p Single Episode", "[480p] Single Episode"),
                        short=[{"label": "[480p] Single Episode", "url": "u", "short": "https://arolinks.com/aaa"},
                               {"label": "720p Zip File", "url": "u", "short": "https://arolinks.com/bbb"}])
        self.assertTrue(any("[ or ]" in e for e in self.run_check()))

    def test_title_and_poster(self):
        self.setup_task(data={"title": "Totally Different", "audio": "Hindi Dubbed", "episodes": "16", "genre": "Action, Comedy", "poster": "http://x/p.jpg"},
                        cap=caption(title="Totally Different"))
        errs = self.run_check()
        self.assertTrue(any("does not match requested" in e for e in errs))
        self.assertTrue(any("poster" in e for e in errs))

    def test_unbalanced_posts(self):
        self.setup_task(short=[{"label": f"L{i}", "url": f"u{i}", "short": f"https://arolinks.com/{i:03d}"} for i in range(6)])
        mk = lambda ids: caption(links=[(f"L{i}", f"https://arolinks.com/{i:03d}") for i in ids])  # noqa: E731
        (self.task / "caption1.txt").write_text(mk([0, 1, 2, 3, 4]), encoding="utf-8")
        (self.task / "caption2.txt").write_text(mk([5]), encoding="utf-8")
        self.assertTrue(any("balanced" in e for e in self.run_check()))


class TestSend(Base):
    def setup_task(self, n=2, poster=None):
        self.jwrite("data.json", {"title": "My Demon", "poster": poster or self.base + "/p.png"})
        for i in range(1, n + 1):
            (self.task / f"caption{i}.txt").write_text(caption(), encoding="utf-8")

    def send(self, *extra):
        return self.out(load("telegram-send", "send").main, "--task", str(self.task), *extra)

    def test_all_channels_all_posts_then_no_duplicates(self):
        self.setup_task()
        rc, out = self.send()
        self.assertEqual(rc, 0); self.assertIn("ok=4 fail=0 channels=2 posts=2", out)
        self.assertEqual(len(S.calls), 4)
        rc, out = self.send()
        self.assertEqual(rc, 0); self.assertIn("SKIP", out); self.assertEqual(len(S.calls), 4)   # nothing resent
        self.send("--force"); self.assertEqual(len(S.calls), 8)
        self.assertNotIn("TGTOK", out)

    def test_upload_fallback_when_url_rejected(self):
        os.environ["DRAMA_POST_CHANNEL_IDS"] = "-1"
        S.reject_url = True; self.setup_task(n=1)
        rc, _ = self.send()
        self.assertEqual((rc, S.calls), (0, [("-1", "url"), ("-1", "file")]))

    def test_partial_failure_then_resume_only_missing(self):
        S.fail_chats.add("-2"); self.setup_task()
        rc, out = self.send()
        self.assertEqual(rc, 1); self.assertIn("FAIL -2 post1 Bad Request: chat not found", out); self.assertIn("ok=2 fail=2", out)
        S.fail_chats.clear(); S.calls.clear()
        rc, _ = self.send()
        self.assertEqual((rc, [c for c, _ in S.calls]), (0, ["-2", "-2"]))

    def test_refuses_oversize_caption_and_missing_token(self):
        self.setup_task(n=1); (self.task / "caption1.txt").write_text("x" * 1100)
        rc, out = self.send(); self.assertEqual(rc, 2); self.assertIn("1024", out); self.assertEqual(S.calls, [])
        os.environ.pop("TELEGRAM_BOT_TOKEN"); self.assertEqual(self.send()[0], 2)


class TestCleanupAndMeasure(Base):
    def test_cleanup_age_dry_run_and_safety(self):
        cl = load("content-cleanup", "cleanup")
        work = self.tmp / "data" / "work"
        old, new = work / "old", work / "new"
        for d in (old, new):
            d.mkdir(); (d / "f.txt").write_text("x")
        t = time.time() - 3 * 86400
        os.utime(old / "f.txt", (t, t)); os.utime(old, (t, t))
        (self.tmp / "data" / "learned").mkdir(); (self.tmp / "data" / "learned" / "n.md").write_text("keep")
        outside = self.tmp / "outside"; outside.mkdir(); (outside / "f").write_text("x"); os.utime(outside / "f", (t, t)); os.utime(outside, (t, t))
        (work / "link").symlink_to(outside)
        rc, out = self.out(cl.main, "--dry-run")
        self.assertIn("would remove 1", out); self.assertTrue(old.exists())
        rc, out = self.out(cl.main, "--hours", "24")
        self.assertFalse(old.exists()); self.assertTrue(new.exists())
        self.assertTrue(outside.exists()); self.assertTrue((self.tmp / "data" / "learned" / "n.md").exists())

    def test_measure(self):
        m = load("drama-format", "measure")
        self.assertEqual(m.plan(13), [7, 6]); self.assertEqual(m.plan(25), [9, 8, 8]); self.assertEqual(m.plan(1), [1])
        self.assertEqual(m.units("📁a"), 3)


if __name__ == "__main__":
    unittest.main()
