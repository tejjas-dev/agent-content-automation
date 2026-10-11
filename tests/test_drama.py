import json
import os
import time
import unittest
from pathlib import Path

from common import Base, S, DATA, load


def old(p, days=3):
    t = time.time() - days * 86400
    for r, ds, fs in os.walk(p):
        for n in ds + fs:
            os.utime(os.path.join(r, n), (t, t))
    os.utime(p, (t, t))


class TestHelper(Base):
    def d(self, *a):
        return self.out(load("drama-post", "drama").main, *a)

    def test_env_task_and_legacy_migration(self):
        home = self.tmp / "home"; (home / ".devx-content" / "learned").mkdir(parents=True)
        (home / ".devx-content" / "learned" / "katdrama.md").write_text("note")
        (home / ".devx-content" / "posted.jsonl").write_text('{"ts": 1}\n')
        old_home, os.environ["HOME"] = os.environ.get("HOME"), str(home)
        try:
            rc, out = self.d("env")
            kv = dict(l.split("=", 1) for l in out.splitlines())
            self.assertEqual((kv["DATA"], kv["ROOT"]), (str(self.data), str(self.root)))
            self.assertTrue(kv["SK"].endswith("skills")); self.assertTrue(kv["PY"])
            self.assertEqual((self.root / "state" / "learned" / "katdrama.md").read_text(), "note")
            self.assertTrue((self.root / "state" / "posted.jsonl").exists())
            rc, out = self.d("task", "My Demon [Hindi]!")
            p = Path(out.strip())
            self.assertTrue(p.is_dir()); self.assertEqual(p.parent, self.root / "work"); self.assertTrue(p.name.endswith("my-demon-hindi"))
        finally:
            os.environ["HOME"] = old_home

    def test_queue_one_runner_others_wait(self):
        self.assertIn("RUNNER queued=2", self.d("enqueue", "A", "B")[1])
        self.assertIn("QUEUED position=3 added=1", self.d("enqueue", "C")[1])       # second message while busy
        self.assertEqual(self.d("next")[1].strip(), "A")
        self.assertIn("QUEUED position=4", self.d("enqueue", "D")[1])               # A running, B C ahead
        self.assertIn("DUPLICATE a", self.d("enqueue", "a")[1])                      # A is being processed
        self.assertEqual([self.d("next")[1].strip() for _ in range(3)], ["B", "C", "D"])
        self.assertEqual(self.d("next")[1].strip(), "EMPTY")
        self.assertIn("runner=idle", self.d("status")[1])
        self.assertIn("RUNNER", self.d("enqueue", "E")[1])                           # idle again: new runner

    def test_batch_limit_and_resume(self):
        out = self.d("enqueue", *[f"T{i}" for i in range(7)])[1]
        self.assertEqual(out.count("SKIPPED_LIMIT"), 2); self.assertIn("RUNNER queued=5", out)
        self.assertEqual(self.d("enqueue")[1].strip(), "QUEUED position=6 added=0")   # no titles while runner alive
        os.environ["DEVX_RUNNER_STALE"] = "0"                                          # runner died
        self.assertIn("RUNNER queued=5", self.d("enqueue")[1])                         # plain resume

    def test_dead_runner_current_title_retried_once_then_dropped(self):
        self.d("enqueue", "X", "Y"); self.assertEqual(self.d("next")[1].strip(), "X")
        os.environ["DEVX_RUNNER_STALE"] = "0"
        self.assertIn("RUNNER", self.d("enqueue", "Z")[1])
        self.assertEqual(self.d("next")[1].strip(), "X")                               # retried first
        out = self.d("enqueue", "W")[1]
        self.assertIn("DROPPED_STALE X", out)                                          # crashed twice: give up
        self.assertEqual([self.d("next")[1].strip() for _ in range(3)], ["Y", "Z", "W"])

    def test_reset(self):
        self.d("enqueue", "A", "B"); self.d("reset", "--queue")
        self.assertIn("queued=0", self.d("status")[1]); self.assertIn("runner=idle", self.d("status")[1])

    def test_notify(self):
        self.assertIn("NOTIFY_SKIPPED", self.d("notify", "hi")[1])
        os.environ["DEVX_NOTIFY_CHAT_ID"] = "42"
        self.assertIn("NOTIFY_OK", self.d("notify", "katdrama domain badla")[1])
        self.assertEqual((S.messages[0]["chat_id"], S.messages[0]["text"]), (["42"], ["katdrama domain badla"]))
        os.environ["DEVX_TELEGRAM_API"] = "http://127.0.0.1:9"
        out = self.d("notify", "x")[1]
        self.assertIn("NOTIFY_FAILED", out); self.assertNotIn("TGTOK", out)

    def test_domains(self):
        self.assertEqual(self.d("domain", "get", "katdrama")[1].strip(), "https://new.katdrama.my/")
        self.assertEqual(self.d("domain", "get", "katworld")[1].strip(), "https://katworld.net/?type=KatDrama")
        self.assertIn("saved", self.d("domain", "set", "katdrama", "https://kd.example/")[1])
        self.assertEqual(self.d("domain", "get", "katdrama")[1].strip(), "https://kd.example/")
        self.assertEqual(self.d("domain", "get", "katworld")[1].strip(), "https://katworld.net/?type=KatDrama")
        self.assertEqual(self.d("domain", "set", "katdrama", "http://bad")[0], 2)
        self.assertEqual(self.d("domain", "get", "nope")[0], 2)


class TestPublish(Base):
    def setup_task(self, labels=("480p Single Episode", "720p Zip File", "1080p Zip File")):
        self.jwrite("data.json", {**DATA, "poster": "https://127.0.0.1:1/p.png"})
        shorts = [{"label": l, "url": f"u{i}", "short": f"https://arolinks.com/{i:07d}"} for i, l in enumerate(labels)]
        self.jwrite("short.json", shorts)

    def pub(self, *extra):
        return self.out(load("drama-post", "publish").main, "--task", str(self.task), "--title", "my demon", *extra)

    def test_full_chain_then_dedupe_and_ledger_lives_in_state(self):
        self.setup_task()
        rc, out = self.pub()
        self.assertEqual(rc, 0); self.assertIn("REPLY ✅ Post bhej diya: My Demon → 2 channel(s), 1 post(s).", out)
        self.assertEqual(len(S.calls), 2)
        self.assertTrue((self.root / "state" / "posted.jsonl").exists())
        rc, out = self.pub(); self.assertEqual((rc, len(S.calls)), (0, 2)); self.assertIn("SKIP", out)

    def test_verify_failure_sends_nothing(self):
        self.setup_task()
        self.jwrite("data.json", {**DATA, "title": "Totally Different Show", "poster": "https://127.0.0.1:1/p.png"})
        rc, out = self.pub()
        self.assertEqual(rc, 1); self.assertIn("REPLY Post format nahi ban paya:", out); self.assertEqual(S.calls, [])

    def test_no_links_and_partial_and_total_send_failure(self):
        self.jwrite("data.json", {**DATA, "poster": "https://127.0.0.1:1/p.png"})
        self.jwrite("short.json", [{"label": "a", "url": "u", "short": None}])
        self.assertIn("REPLY Links short nahi ho paye.", self.pub()[1])
        self.setup_task(); S.fail_chats.add("-2")
        rc, out = self.pub()
        self.assertEqual(rc, 1); self.assertIn("REPLY ⚠️ My Demon: 1/2 post gaye. Fail: -2 — Bad Request: chat not found.", out)
        S.fail_chats.update({"-1"})
        self.assertIn("REPLY Channel me post send nahi ho paya: -1 — Bad Request: chat not found.", self.pub("--force")[1])


class TestCleanup(Base):
    def cl(self, *a):
        return self.out(load("content-cleanup", "cleanup").main, *a)

    def make(self):
        w = self.root / "work"
        for n in ("old1", "new1"):
            (w / n).mkdir(); (w / n / "f.txt").write_text("x")
        (self.root / "stray.py").write_text("x")
        (self.root / "state" / "learned").mkdir(); (self.root / "state" / "learned" / "k.md").write_text("keep")
        (self.root / "state" / "posted.jsonl").write_text(json.dumps({"ts": 1}) + "\n" + json.dumps({"ts": int(time.time())}) + "\n")
        old(w / "old1"); old(self.root / "stray.py")
        outside = self.tmp / "outside"; outside.mkdir(); (outside / "f").write_text("x")
        (w / "link").symlink_to(outside)
        return w, outside

    def test_age_based_and_state_kept(self):
        w, outside = self.make()
        self.assertIn("would remove 3", self.cl("--dry-run")[1]); self.assertTrue((w / "old1").exists())
        rc, out = self.cl("--hours", "6")
        self.assertFalse((w / "old1").exists()); self.assertFalse((self.root / "stray.py").exists())
        self.assertTrue((w / "new1").exists()); self.assertFalse((w / "link").exists()); self.assertTrue((outside / "f").exists())
        self.assertTrue((self.root / "state" / "learned" / "k.md").exists())
        self.assertEqual(len((self.root / "state" / "posted.jsonl").read_text().splitlines()), 1)     # 30d prune
        self.assertIn("ledger pruned 1", out)

    def test_full_wipe_keeps_state_and_respects_live_runner(self):
        self.make()
        (self.root / "state" / "runner.json").write_text(json.dumps({"ts": time.time(), "current": "X"}))
        self.assertIn("runner is active", self.cl("--hours", "0")[1]); self.assertTrue((self.root / "work" / "new1").exists())
        self.cl("--hours", "0", "--force")
        self.assertEqual(list((self.root / "work").iterdir()), [])
        self.assertTrue((self.root / "state" / "learned" / "k.md").exists())

    def test_missing_folder(self):
        import shutil
        shutil.rmtree(self.root)
        self.assertIn("nothing to clean", self.cl()[1])


class TestFetch(Base):
    def f(self, path, *a):
        return self.out(load("drama-scrape", "fetch").main, self.base + path, str(self.task / "o.html"), *a)

    def test_http_ok_blocked_dead_and_missing_engine(self):
        rc, out = self.f("/page")
        self.assertEqual(rc, 0); self.assertIn("OK tier=http status=200", out); self.assertIn("Hello Page", out)
        self.assertIn("Hello Page", (self.task / "o.html").read_text())
        rc, out = self.f("/blocked"); self.assertEqual(rc, 1); self.assertIn("reason=blocked (try --tier stealth)", out)
        rc, out = self.out(load("drama-scrape", "fetch").main, "http://127.0.0.1:9/x", str(self.task / "o2.html"), "--timeout", "2")
        self.assertEqual(rc, 1); self.assertIn("FAIL tier=http", out)
        rc, out = self.f("/page", "--tier", "stealth"); self.assertEqual(rc, 1); self.assertIn("scrapling_missing", out)


if __name__ == "__main__":
    unittest.main()
