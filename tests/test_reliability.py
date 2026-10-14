import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from common import Base, S, DATA, caption, load

GOOD = "<html><head><title>Good</title></head><body>" + "x" * 300 + "</body></html>"
SHELL = "<html><body><h1>Search Results</h1><p>Loading...</p></body></html>" + " " * 300
BLOCK = "<html><title>Just a moment...</title></html>"


def age(path, hours):
    t = time.time() - hours * 3600
    for r, ds, fs in os.walk(path):
        for n in ds + fs:
            os.utime(os.path.join(r, n), (t, t))
    os.utime(path, (t, t))


class TestFetchResilience(Base):
    def run_fetch(self, script, *args):
        """script: {tier: [(status, html) | Exception, ...]} consumed in order per tier."""
        m = load("drama-scrape", "fetch")
        calls = []

        def fake(url, tier, wait, timeout):
            calls.append(tier)
            step = script[tier].pop(0)
            if isinstance(step, Exception):
                raise step
            return step[0], step[1], url
        m.get = fake
        rc, out = self.out(m.main, "http://site.test/x", str(self.task / "o.html"), *args)
        return rc, out, calls

    def test_auto_climbs_when_blocked_or_js_shell(self):
        rc, out, calls = self.run_fetch({"http": [(403, BLOCK)], "dynamic": [(200, SHELL)], "stealth": [(200, GOOD)]}, "--tier", "auto")
        self.assertEqual((rc, calls), (0, ["http", "dynamic", "stealth"])); self.assertIn("OK tier=stealth", out)
        self.assertIn("Good", (self.task / "o.html").read_text())

    def test_auto_stops_at_the_first_good_tier(self):
        rc, out, calls = self.run_fetch({"http": [(200, SHELL)], "dynamic": [(200, GOOD)], "stealth": []}, "--tier", "auto")
        self.assertEqual((rc, calls), (0, ["http", "dynamic"]))

    def test_transient_errors_retry_then_report_code(self):
        rc, out, calls = self.run_fetch({"http": [(503, "x" * 3500), (503, "x" * 3500)]})
        self.assertEqual((rc, calls), (1, ["http", "http"])); self.assertIn("code=HTTP_503", out)
        rc, out, calls = self.run_fetch({"http": [TimeoutError("timed out"), (200, GOOD)]})
        self.assertEqual((rc, calls), (0, ["http", "http"]))                     # second try works
        rc, out, calls = self.run_fetch({"http": [TimeoutError("timed out"), TimeoutError("timed out")]})
        self.assertIn("code=TIMEOUT", out)

    def test_no_retry_for_404_and_blocked_explicit_tier(self):
        rc, out, calls = self.run_fetch({"http": [(404, "x" * 400)]})
        self.assertEqual((rc, calls), (1, ["http"])); self.assertIn("code=NOT_FOUND", out)
        rc, out, calls = self.run_fetch({"http": [(403, BLOCK)]})
        self.assertEqual(calls, ["http"]); self.assertIn("reason=blocked (try --tier stealth) code=BLOCKED", out)

    def test_attempt_budget_and_missing_engine(self):
        rc, out, calls = self.run_fetch({"http": [(403, BLOCK)], "dynamic": [(403, BLOCK)], "stealth": [(403, BLOCK)]}, "--tier", "auto", "--max-attempts", "2")
        self.assertEqual(calls, ["http", "dynamic"]); self.assertIn("code=ATTEMPTS_EXHAUSTED", out)
        rc, out, calls = self.run_fetch({"stealth": [ImportError("scrapling")]}, "--tier", "stealth")
        self.assertIn("code=NOT_INSTALLED", out); self.assertEqual(calls, ["stealth"])    # never retried

    def test_js_shell_is_flagged_on_explicit_http(self):
        rc, out = self.out(load("drama-scrape", "fetch").main, self.base + "/shell", str(self.task / "o.html"))
        self.assertEqual(rc, 0); self.assertIn("note=js_shell(use --tier dynamic)", out)

    def test_failures_are_logged_without_secrets(self):
        self.run_fetch({"http": [(404, "x" * 400)]})
        log = (self.root / "state" / "logs" / "events.jsonl").read_text()
        self.assertIn("NOT_FOUND", log); self.assertNotIn("TGTOK", log)


class TestShortenResilience(Base):
    def run_short(self, items):
        self.jwrite("links.json", items)
        rc, out = self.out(load("link-short", "shorten").main, str(self.task / "links.json"))
        return rc, out, json.loads((self.task / "short.json").read_text())

    def test_auth_error_stops_at_once(self):
        os.environ["AROLINKS_TOKEN"] = "WRONG"; S.short_body = "Invalid API token"
        rc, out, res = self.run_short([{"label": "a", "url": "https://x.test/1"}, {"label": "b", "url": "https://x.test/2"}])
        self.assertEqual(rc, 1); self.assertIn("reasons: auth=2", out); self.assertIn("CODE=AUTH", out)
        self.assertEqual(len(S.short_hits), 2)                                    # no retry rounds
        self.assertNotIn("WRONG", out); self.assertTrue(all(r["short"] is None for r in res))

    def test_unknown_and_rate_errors_are_retried_with_backoff(self):
        S.short_fail.add("https://x.test/1")
        rc, out, res = self.run_short([{"label": "a", "url": "https://x.test/1"}, {"label": "b", "url": "https://x.test/2"}])
        self.assertEqual(rc, 0); self.assertIn("reasons: unknown=1", out)
        self.assertEqual(S.short_hits.count("https://x.test/1"), 3)                # first pass + 2 retry rounds (DEVX_RETRIES=2)
        self.assertEqual(S.short_hits.count("https://x.test/2"), 1)                # successes are not repeated
        S.short_hits.clear(); S.short_status = 429
        rc, out, _ = self.run_short([{"label": "a", "url": "https://x.test/1"}])
        self.assertEqual(rc, 1); self.assertIn("CODE=RATE", out); self.assertEqual(len(S.short_hits), 3)

    def test_backoff_sleeps_grow(self):
        m = load("link-short", "shorten"); slept = []
        os.environ["DEVX_BACKOFF"] = "2"; os.environ["DEVX_RETRIES"] = "3"
        S.short_fail.add("https://x.test/1"); self.jwrite("links.json", [{"label": "a", "url": "https://x.test/1"}])
        with mock.patch.object(m.time, "sleep", slept.append):
            self.out(m.main, str(self.task / "links.json"))
        self.assertEqual(len(slept), 3)
        for n, s in enumerate(slept):
            self.assertTrue(2 * 2 ** n * 0.5 <= s <= 2 * 2 ** n, (n, s))          # 1-2 s, 2-4 s, 4-8 s

    def test_invalid_urls_never_reach_the_api(self):
        rc, out, res = self.run_short([{"label": "ok", "url": "https://x.test/1"}, {"label": "bad", "url": "ftp://x.test/2"},
                                       {"label": "js", "url": "javascript:alert(1)"}])
        self.assertEqual(rc, 0); self.assertIn("shortened 1/3", out); self.assertIn("invalid_url=2", out)
        self.assertEqual(S.short_hits, ["https://x.test/1"]); self.assertEqual([r["short"] is None for r in res], [False, True, True])

    def test_token_with_newline_is_stripped(self):
        os.environ["AROLINKS_TOKEN"] = "AROTOK \n"
        rc, out, res = self.run_short([{"label": "a", "url": "https://x.test/1"}])
        self.assertEqual(rc, 0)


class TestSendResilience(Base):
    def setup_task(self, name="t1", poster=None):
        task = self.root / "work" / name; task.mkdir(parents=True, exist_ok=True)
        self.jwrite("data.json", {"title": "My Demon", "poster": poster or self.base + "/p.png"}, task)
        (task / "caption1.txt").write_text(caption(), encoding="utf-8")
        return task

    def send(self, task, *extra, mod=None):
        return self.out((mod or load("telegram-send", "send")).main, "--task", str(task), *extra)

    def test_same_drama_requested_again_is_sent_again(self):
        t1, t2 = self.setup_task("t1"), self.setup_task("t2")
        self.assertIn("ok=2 fail=0", self.send(t1)[1])
        rc, out = self.send(t2)                                                   # a NEW request (new task) for the same drama
        self.assertEqual(rc, 0); self.assertNotIn("SKIP", out); self.assertEqual(len(S.calls), 4)
        self.assertIn("SKIP", self.send(t2)[1]); self.assertEqual(len(S.calls), 4)  # but a rerun of the same task only fills gaps
        ledger = [json.loads(l) for l in (self.root / "state" / "posted.jsonl").read_text().splitlines()]
        self.assertEqual({r["task"] for r in ledger}, {"t1", "t2"})

    def test_read_timeout_is_never_blindly_retried(self):
        task = self.setup_task(); m = load("telegram-send", "send"); real, seen = m.call, []

        def fake(method, data, headers=None, timeout=60):
            if b"chat_id=-2" in (data or b""):
                seen.append("-2"); return {"ok": False, "description": "timed out", "_timeout": True}
            return real(method, data, headers, timeout)
        m.call = fake
        rc, out = self.send(task, mod=m)
        self.assertEqual(rc, 1); self.assertIn("FAIL -2 post1 timeout_uncertain", out); self.assertIn("OK   -1 post1", out)
        self.assertEqual(seen, ["-2"])                                            # one attempt, no resend, no upload fallback
        self.assertEqual([json.loads(l)["channel"] for l in (self.root / "state" / "posted.jsonl").read_text().splitlines()], ["-1"])
        self.assertIn("SEND_FAIL", (self.root / "state" / "logs" / "events.jsonl").read_text())

    def test_retry_after_is_respected_and_backoff_without_it(self):
        os.environ["DEVX_RETRY_CAP"] = "30"; os.environ["DEVX_BACKOFF"] = "2"; os.environ["DRAMA_POST_CHANNEL_IDS"] = "-1"
        task = self.setup_task(); m = load("telegram-send", "send"); slept = []
        answers = iter([{"ok": False, "description": "Too Many Requests", "parameters": {"retry_after": 7}},
                        {"ok": False, "description": "Bad Gateway"}, {"ok": True}])
        m.call = lambda *a, **k: next(answers)
        with mock.patch.object(m.time, "sleep", slept.append):
            rc, out = self.send(task, mod=m)
        self.assertEqual(rc, 0); self.assertEqual(slept[0], 7.0)                  # Telegram's retry_after wins
        self.assertTrue(2 <= slept[1] <= 4, slept)                                # attempt 2 without retry_after: 2*2^1 with jitter

    def test_token_with_trailing_whitespace_and_secret_never_printed(self):
        os.environ["TELEGRAM_BOT_TOKEN"] = "TGTOK\n"
        rc, out = self.send(self.setup_task())
        self.assertEqual(rc, 0, out); self.assertNotIn("TGTOK", out)


class TestPublishResilience(Base):
    def setup_task(self, labels=("480p Single Episode", "720p Zip File")):
        self.jwrite("data.json", {**DATA, "poster": "https://127.0.0.1:1/p.png"})
        self.jwrite("short.json", [{"label": l, "url": f"u{i}", "short": f"https://arolinks.com/{i:07d}"} for i, l in enumerate(labels)])

    def pub(self, *extra, mod=None):
        return self.out((mod or load("drama-post", "publish")).main, "--task", str(self.task), "--title", "my demon", *extra)

    def test_dry_run_sends_nothing_and_writes_no_ledger(self):
        self.setup_task()
        rc, out = self.pub("--dry-run")
        self.assertEqual(rc, 0); self.assertIn("REPLY (dry-run) Post ready: My Demon -> 1 post(s)", out)
        self.assertEqual(S.calls, []); self.assertFalse((self.root / "state" / "posted.jsonl").exists())
        self.assertFalse((self.task / ".done").exists())

    def test_done_marker_and_second_run_says_nothing_new_was_sent(self):
        self.setup_task()
        self.assertIn("REPLY ✅ Post bhej diya", self.pub()[1]); self.assertTrue((self.task / ".done").exists())
        rc, out = self.pub()
        self.assertEqual(rc, 0); self.assertIn("pehle hi bhej diya tha", out); self.assertNotIn("✅", out); self.assertEqual(len(S.calls), 2)

    def test_verify_failure_marks_task_failed(self):
        self.setup_task(); self.jwrite("data.json", {**DATA, "title": "Totally Different Show", "poster": "https://127.0.0.1:1/p.png"})
        self.assertEqual(self.pub()[0], 1); self.assertTrue((self.task / ".failed").exists())

    def test_subprocess_timeout_and_crash_give_a_reply_not_a_traceback(self):
        self.setup_task(); m = load("drama-post", "publish"); real = m.run

        def fake(script, *a, timeout=120):
            if script.startswith("telegram-send"):
                return 124, f"timeout after {timeout}s"
            return real(script, *a, timeout=timeout)
        m.run = fake
        rc, out = self.pub(mod=m)
        self.assertEqual(rc, 1); self.assertIn("REPLY Channel me post send timeout hua", out)
        m.run = lambda script, *a, timeout=120: (125, "cannot run") if script.startswith("drama-format") else real(script, *a, timeout=timeout)
        rc, out = self.pub(mod=m)
        self.assertEqual(rc, 1); self.assertIn("REPLY Post format nahi ban paya", out); self.assertTrue((self.task / ".failed").exists())

    def test_partial_send_keeps_task_resumable(self):
        self.setup_task(); S.fail_chats.add("-2")
        self.assertEqual(self.pub()[0], 1)
        self.assertFalse((self.task / ".done").exists()); self.assertFalse((self.task / ".failed").exists())   # send problems are not data problems
        S.fail_chats.clear(); S.calls.clear()
        rc, out = self.pub()
        self.assertEqual((rc, [c for c, _ in S.calls]), (0, ["-2"]))               # only the missing channel
        self.assertTrue((self.task / ".done").exists())


class TestDramaResilience(Base):
    def d(self, *a):
        return self.out(load("drama-post", "drama").main, *a)

    def test_damaged_queue_line_does_not_empty_the_queue(self):
        q = self.root / "state" / "queue.jsonl"
        q.write_text('{"title": "A"}\nNOT JSON\n{"title": "B"}\n[1,2]\n', encoding="utf-8")
        self.assertIn("queued=2", self.d("status")[1])
        self.assertTrue((self.root / "state" / "queue.jsonl.bad").exists())
        self.assertIn("NOT JSON", (self.root / "state" / "queue.jsonl.bad").read_text())
        out = self.d("enqueue", "C")[1]
        self.assertIn("RUNNER queued=3", out)
        self.assertEqual([self.d("next")[1].strip() for _ in range(3)], ["A", "B", "C"])
        self.assertFalse(list((self.root / "state").glob("*.tmp")))                # atomic writes leave no temp files

    def test_task_is_reused_until_done_or_failed(self):
        t1 = self.d("task", "My Demon")[1].strip()
        self.assertEqual(self.d("task", "My Demon")[1].strip(), t1)                # crash resume: same folder
        (self.task.parent / t1.split("/")[-1] / ".done").touch()
        t2 = self.d("task", "My Demon")[1].strip(); self.assertNotEqual(t2, t1)   # finished: a new request is a new task
        os.makedirs(t2, exist_ok=True); open(os.path.join(t2, ".failed"), "w").close()
        t3 = self.d("task", "My Demon")[1].strip(); self.assertNotIn(t3, (t1, t2))  # bad data: scrape fresh
        self.assertNotEqual(self.d("task", "Other Show")[1].strip(), t3)
        self.assertNotEqual(self.d("task", "My Demon", "--fresh")[1].strip(), t3)
        old_dir = self.d("task", "Old One")[1].strip(); age(Path(old_dir), 48)
        self.assertNotEqual(self.d("task", "Old One")[1].strip(), old_dir)         # too old to resume (DEVX_TASK_REUSE 6 h)

    def test_step_follows_the_files(self):
        t = self.task
        steps = lambda: self.d("step", str(t))[1].strip()  # noqa: E731
        self.assertEqual(steps(), "STEP FIND")
        (t / "find.txt").write_text("source=primary\npage_url=https://x.test/a\n"); self.assertEqual(steps(), "STEP SCRAPE")
        self.jwrite("data.json", {"title": "T", "poster": "https://x.test/p.jpg"}); self.assertEqual(steps(), "STEP SCRAPE")    # no links yet
        self.jwrite("links.json", [{"label": "a", "url": "https://x.test/1"}]); self.assertEqual(steps(), "STEP SHORT")
        self.jwrite("short.json", [{"label": "a", "url": "u", "short": None}]); self.assertEqual(steps(), "STEP SHORT")      # nothing shortened
        self.jwrite("short.json", [{"label": "a", "url": "u", "short": "https://arolinks.com/a"}]); self.assertEqual(steps(), "STEP PUBLISH")
        (t / "short.json").write_text("{broken"); self.assertEqual(steps(), "STEP SHORT")                                     # damaged file = redo that step
        (t / ".done").touch(); self.assertEqual(steps(), "STEP DONE")

    def test_log_redacts_secrets_and_status_shows_recent_errors(self):
        self.d("log", "send", "SEND_FAIL", "token TGTOK and AROTOK leaked")
        self.d("log", "fetch", "OK", "fine")
        log = (self.root / "state" / "logs" / "events.jsonl").read_text()
        self.assertNotIn("TGTOK", log); self.assertNotIn("AROTOK", log); self.assertIn("***", log)
        out = self.d("status")[1]
        self.assertIn("recent: send/SEND_FAIL", out); self.assertNotIn("recent: fetch/OK", out)

    def test_notify_is_optional(self):
        self.assertIn("NOTIFY_SKIPPED", self.d("notify", "x")[1])
        os.environ["DEVX_NOTIFY_CHAT_ID"] = "42\n"; os.environ["TELEGRAM_BOT_TOKEN"] = "TGTOK \n"
        self.assertIn("NOTIFY_OK", self.d("notify", "hello")[1])


class TestCleanup24h(Base):
    def cl(self, *a):
        return self.out(load("content-cleanup", "cleanup").main, *a)

    def age(self, path, hours):
        age(path, hours)

    def test_default_is_24_hours(self):
        w = self.root / "work"
        for n, h in (("fresh", 1), ("day", 20), ("stale", 30)):
            (w / n).mkdir(); (w / n / "page.html").write_text("x"); self.age(w / n, h)
        out = self.cl("--no-browser-temp")[1]
        self.assertEqual(sorted(p.name for p in w.iterdir() if p.name != "t1"), ["day", "fresh"]); self.assertIn("removed 1", out)

    def test_state_housekeeping_keeps_what_matters(self):
        st, now = self.root / "state", time.time()
        (st / "learned").mkdir(); (st / "learned" / "k.md").write_text("keep")
        (st / "queue.jsonl").write_text('{"title": "A"}\n'); (st / "domains.json").write_text("{}")
        (st / "logs").mkdir()
        (st / "logs" / "events.jsonl").write_text(json.dumps({"ts": now - 9 * 86400, "code": "X"}) + "\n" + json.dumps({"ts": now, "code": "Y"}) + "\n")
        for sub, name, days in (("view", "v_old", 2), ("view", "v_new", 0), ("backup", "b_old", 8), ("backup", "b_new", 1),
                                ("patches", "p_old", 31), ("patches", "p_new", 5)):
            d = st / sub / name; d.mkdir(parents=True); (d / "f").write_text("x"); self.age(d, days * 24)
        for name, status, days in (("d_fail_old", "failed", 4), ("d_fail_new", "failed", 1), ("d_ready_old", "ready", 40)):
            d = st / "draft" / name; d.mkdir(parents=True); (d / "meta.json").write_text(json.dumps({"status": status})); self.age(d, days * 24)
        self.cl("--no-browser-temp")
        left = lambda sub: sorted(p.name for p in (st / sub).iterdir())  # noqa: E731
        self.assertEqual(left("view"), ["v_new"]); self.assertEqual(left("backup"), ["b_new"]); self.assertEqual(left("patches"), ["p_new"])
        self.assertEqual(left("draft"), ["d_fail_new", "d_ready_old"])           # a draft waiting for approval is never auto-deleted
        self.assertEqual(len((st / "logs" / "events.jsonl").read_text().splitlines()), 1)
        self.assertEqual(((st / "learned" / "k.md").read_text(), (st / "queue.jsonl").read_text(), (st / "domains.json").read_text()), ("keep", '{"title": "A"}\n', "{}"))

    def test_browser_temp_folders_and_quiet_mode(self):
        tmp = self.tmp / "systmp"; tmp.mkdir()
        old_tmp, tempfile.tempdir = tempfile.tempdir, str(tmp)
        try:
            for n, h in (("playwright_chromiumdev_profile-old", 30), ("playwright_chromiumdev_profile-new", 2), ("my-own-folder", 99)):
                (tmp / n).mkdir(); (tmp / n / "f").write_text("x"); self.age(tmp / n, h)
            self.assertIn("browser temp 1", self.cl()[1])
            self.assertEqual(sorted(p.name for p in tmp.iterdir()), ["my-own-folder", "playwright_chromiumdev_profile-new"])   # only scraper leftovers go
            (tmp / "playwright-artifacts-x").mkdir(); self.age(tmp / "playwright-artifacts-x", 40)
            self.cl("--no-browser-temp"); self.assertTrue((tmp / "playwright-artifacts-x").exists())
        finally:
            tempfile.tempdir = old_tmp
        self.assertEqual(self.cl("--quiet", "--no-browser-temp")[1], "")           # nothing to do: cron prints nothing
        self.assertIn("removed", self.cl("--no-browser-temp")[1])

    def test_ledger_retention_is_configurable(self):
        led = self.root / "state" / "posted.jsonl"
        led.write_text(json.dumps({"ts": time.time() - 40 * 86400}) + "\n" + json.dumps({"ts": time.time()}) + "\n")
        os.environ["DEVX_LEDGER_DAYS"] = "90"
        try:
            self.cl("--no-browser-temp"); self.assertEqual(len(led.read_text().splitlines()), 2)
            os.environ["DEVX_LEDGER_DAYS"] = "30"
            self.cl("--no-browser-temp"); self.assertEqual(len(led.read_text().splitlines()), 1)
        finally:
            os.environ.pop("DEVX_LEDGER_DAYS", None)

    def test_type_must_be_a_plain_folder_name(self):
        outside = self.tmp / "outside"; outside.mkdir(); (outside / "keep.txt").write_text("x"); self.age(outside / "keep.txt", 100)
        for bad in ("..", "../outside", "a/b", "/etc", "Drama", ""):
            rc, out = self.cl("--type", bad, "--no-browser-temp")
            self.assertEqual(rc, 2, bad); self.assertIn("ERROR", out)
        self.assertTrue((outside / "keep.txt").exists())

    def test_odd_json_lines_in_ledger_and_events_do_not_crash_cleanup(self):
        st = self.root / "state"; (st / "logs").mkdir()
        (st / "posted.jsonl").write_text('5\n"x"\n[1]\n{"ts": "yesterday"}\n' + json.dumps({"ts": time.time()}) + "\n")
        (st / "logs" / "events.jsonl").write_text('7\n[]\n' + json.dumps({"ts": time.time(), "code": "Y"}) + "\n")
        rc, out = self.cl("--no-browser-temp")
        self.assertEqual(rc, 0, out)
        self.assertEqual(len((st / "posted.jsonl").read_text().splitlines()), 1)
        self.assertEqual(len((st / "logs" / "events.jsonl").read_text().splitlines()), 1)


class TestHardening(Base):
    def test_poster_with_a_non_http_scheme_is_never_opened(self):
        m = load("telegram-send", "send")
        self.assertEqual(m.fetch_poster("file:///etc/hostname"), (None, ""))
        self.assertEqual(m.fetch_poster("ftp://x.example/p.png"), (None, ""))
        self.assertEqual(m.fetch_poster(self.base + "/p.png")[1], "image/png")           # a normal http(s) poster still works

    def test_saved_domains_must_pass_the_same_check_as_domain_set(self):
        m = load("drama-post", "drama")
        (self.root / "state" / "domains.json").write_text(json.dumps({
            "primary": "http://plain.example/", "fallback": "https://127.0.0.1/", "finder": "https://user:pw@x.example/"}))
        self.assertEqual(m.domains(), m.DEFAULT_DOMAINS)                                  # all three rejected -> defaults
        (self.root / "state" / "domains.json").write_text(json.dumps({"primary": "https://moved.example/"}))
        self.assertEqual(m.domains()["primary"], "https://moved.example/")


if __name__ == "__main__":
    unittest.main()
