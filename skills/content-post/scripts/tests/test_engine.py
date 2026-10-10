import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fakesite  # noqa: E402
from devx import caption, checks, cli, config, content_types, dom, extract, profile, search, store  # noqa: E402

SPEC = content_types.get("drama")


def prof_json(pid, order, base, mode="template", search_tier="http", extra=None):
    d = {"schema": 1, "id": pid, "type": "drama", "order": order, "entry_urls": [base + "/"],
         "fetch": {"search_tier": search_tier, "detail_tier": "http"},
         "search": {"mode": mode} if mode == "auto" else {"mode": "template", "path": "/?q={query}"}}
    d.update(extra or {})
    return d


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = fakesite.State()
        cls.srv = fakesite.make_server(cls.state)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.src = self.tmp / "sources" / "drama"
        self.src.mkdir(parents=True)
        env = {"DEVX_DATA_DIR": str(self.tmp / "data"), "DEVX_SOURCES_DIR": str(self.tmp / "sources"),
               "DEVX_TEST_ALLOW_HTTP": "1", "DEVX_SEND_DELAY": "0", "DEVX_TITLE_DELAY": "0",
               "DEVX_RETRY_CAP": "0", "AROLINKS_TOKEN": "AROTOK", "TELEGRAM_BOT_TOKEN": "TGTOK",
               "DRAMA_POST_CHANNEL_IDS": "-1,-2", "DEVX_AROLINKS_API": self.base + "/api",
               "DEVX_TELEGRAM_API": self.base}
        self._old = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        self.state.tg_calls.clear()
        self.state.fail_chats.clear()
        self.state.reject_url_mode = False
        self.state.short_fail.clear()
        self.state.home_param = "s"
        self.write_profile(prof_json("primary", 10, self.base))

    def tearDown(self):
        for k, v in self._old.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_profile(self, d):
        (self.src / f"{d['id']}.json").write_text(json.dumps(d))

    def run_cli(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cli.main(list(argv))
        return buf.getvalue()


class TestUnits(unittest.TestCase):
    def test_balanced_split(self):
        for total, want in ((13, [7, 6]), (25, [9, 8, 8]), (12, [12]), (1, [1])):
            self.assertEqual(caption._sizes(total, max(1, -(-total // 12))), want)

    def test_caption_limits_and_format(self):
        links = [(f"Episode {i} Download", f"https://arolinks.com/{i:07d}") for i in range(30)]
        caps = caption.build(SPEC, {"title": "T", "audio": "Hindi", "genre": "A, B"}, links)
        self.assertTrue(all(caption.utf16(c) <= 950 for c in caps))
        self.assertTrue(caps[0].startswith("📺 TITLE : T\n🎙 AUDIO : Hindi\n🎭 GENRE : A, B\n\n📁 "))
        self.assertNotIn("EPISODES", caps[0])
        self.assertEqual(sum(c.count("📁") for c in caps), 30)

    def test_caption_trims_long_labels_and_brackets(self):
        caps = caption.build(SPEC, {"title": "T"}, [("[x]" + "y" * 200, "https://arolinks.com/a")])
        self.assertNotIn("[", caps[0])
        self.assertLess(len(caps[0]), 200)

    def test_caption_header_too_long(self):
        with self.assertRaises(caption.CaptionError):
            caption.build(SPEC, {"title": "T" * 2000}, [("a", "https://arolinks.com/a")])

    def test_checks(self):
        data = {"title": "My Drama", "poster": "https://x/p.jpg"}
        links = [("Ep 1", "https://arolinks.com/a"), ("Ep 2", "https://arolinks.com/b")]
        caps = caption.build(SPEC, data, links)
        self.assertEqual(checks.run(SPEC, data, [u for _, u in links], caps, "My Drama"), [])
        self.assertTrue(checks.run(SPEC, data, ["https://arolinks.com/a"], caps, "My Drama"))
        self.assertTrue(checks.run(SPEC, data, [u for _, u in links], caps, "Totally Other"))
        bad = [caps[0].replace("https://arolinks.com/a", "https://evil.com/a")]
        self.assertTrue(checks.run(SPEC, data, [u for _, u in links], bad, "My Drama"))

    def test_matching(self):
        C = lambda *t: search.rank(Q, [search.Cand(x, f"https://s/{i}") for i, x in enumerate(t)], SPEC.noise)  # noqa
        global Q
        Q = "my unicorn girl"
        self.assertEqual(search.pick(Q, C("My Unicorn Girl (2024) Hindi Dubbed", "Other Show"))[0], "accept")
        Q = "moon tales"
        self.assertEqual(search.pick(Q, C("Moon Tales Season 1", "Moon Tales Season 2"))[0], "ambiguous")
        Q = "moon tales season 2"
        k, v = search.pick(Q, C("Moon Tales Season 1", "Moon Tales Season 2"))
        self.assertEqual((k, v.title), ("accept", "Moon Tales Season 2"))
        Q = "zzz qqq"
        self.assertEqual(search.pick(Q, C("Dream Garden"))[0], "none")
        self.assertEqual(search.relaxed_queries("a bb cccc"), ["a bb cccc", "a bb", "cccc"])

    def test_profile_validation(self):
        good = prof_json("x", 1, "https://e.com")
        self.assertTrue(profile.validate(good)[0])
        self.assertFalse(profile.validate({**good, "bogus": 1})[0])
        self.assertFalse(profile.validate({**good, "entry_urls": ["http://e.com"]})[0])
        self.assertFalse(profile.validate({**good, "detail": {"links": {"css": ["a[["]}}})[0])
        self.assertFalse(profile.validate({**good, "detail": {"links": {"text_include": "(("}}})[0])
        self.assertFalse(profile.validate({**good, "fetch": {"search_tier": "magic"}})[0])
        self.assertFalse(profile.validate({**good, "id": "Bad Id"})[0])

    def test_title_cleaning_and_extraction(self):
        t = extract.clean_title("My Unicorn Girl (2024) Hindi Dubbed Download 720p - KatTest", SPEC.noise, ["KatTest"])
        self.assertEqual(t, "My Unicorn Girl (2024)")
        html = fakesite.detail_html("my-unicorn-girl", fakesite.DRAMAS["my-unicorn-girl"])
        d = extract.extract(html, "https://kat.test/drama/x/", profile.merge({}), SPEC)
        self.assertEqual((d["audio"], d["episodes"], d["genre"]), ("Hindi", "16", "Romance, Fantasy, Comedy"))
        self.assertEqual(len(d["links"]), 14)
        self.assertTrue(all("utm_" not in u and "fbclid" not in u for _, u in d["links"]))
        self.assertNotIn("logo", " ".join(d["poster_candidates"]))


class TestEndToEnd(Base):
    def test_ok_notfound_dedupe_force(self):
        out = self.run_cli("run", "drama", "My Unicorn Girl", "Nothing Here Xyz")
        self.assertIn("✅ Post bhej diya: My Unicorn Girl (2024) → 2 channel(s), 2 post(s).", out)
        self.assertIn("❌ Nothing Here Xyz: Drama nahi mila.", out)
        calls = self.state.tg_calls
        self.assertEqual(len(calls), 4)                                  # 2 channels x 2 posts (14 links -> 7+7)
        self.assertEqual({c["chat"] for c in calls}, {"-1", "-2"})
        cap = calls[0]["caption"]
        self.assertTrue(cap.startswith("📺 TITLE : My Unicorn Girl (2024)\n🎙 AUDIO : Hindi\n📺 EPISODES : 16\n"))
        self.assertEqual(cap.count("📁"), 7)
        self.assertNotIn("drive.google", cap)
        n = len(calls)
        self.assertIn("pehle hi post ho chuka", self.run_cli("run", "drama", "My Unicorn Girl"))
        self.assertEqual(len(self.state.tg_calls), n)                    # no duplicate sends
        self.assertIn("✅", self.run_cli("run", "drama", "My Unicorn Girl", "--force"))
        self.assertEqual(len(self.state.tg_calls), n * 2)
        self.assertFalse(list((Path(os.environ["DEVX_DATA_DIR"]) / "work").iterdir()))   # cleaned

    def test_partial_then_resume(self):
        self.state.fail_chats.add("-2")
        out = self.run_cli("run", "drama", "Moon Tales Season 2")
        self.assertIn("⚠️ Moon Tales Season 2: 1/2 post gaye. Fail: -2 — Bad Request: chat not found", out)
        self.state.fail_chats.clear()
        self.state.tg_calls.clear()
        self.assertIn("✅", self.run_cli("run", "drama", "Moon Tales Season 2"))
        self.assertEqual([c["chat"] for c in self.state.tg_calls], ["-2"])   # only the missing one

    def test_url_mode_rejected_falls_back_to_upload(self):
        self.state.reject_url_mode = True
        os.environ["DRAMA_POST_CHANNEL_IDS"] = "-1"
        self.assertIn("✅", self.run_cli("run", "drama", "Moon Tales Season 2"))
        self.assertEqual([c["mode"] for c in self.state.tg_calls], ["url", "file"])

    def test_ambiguous_and_season_hint(self):
        out = self.run_cli("run", "drama", "Moon Tales")
        self.assertIn("❓ Moon Tales: title ambiguous hai", out)
        self.assertEqual(self.state.tg_calls, [])
        self.assertIn("✅ Post bhej diya: Moon Tales Season 2", self.run_cli("run", "drama", "Moon Tales Season 2"))

    def test_dry_run_sends_nothing(self):
        out = self.run_cli("run", "drama", "Moon Tales Season 2", "--dry-run")
        self.assertIn("🧪 Dry-run OK", out)
        self.assertIn("caption preview", out)
        self.assertEqual(self.state.tg_calls, [])
        self.assertFalse((Path(os.environ["DEVX_DATA_DIR"]) / "posted.jsonl").exists())

    def test_limits_and_budget(self):
        out = self.run_cli("run", "drama", "a1", "a2", "a3", "a4", "a5", "a6", "a7", "--dry-run", "--max", "2")
        self.assertEqual(out.count("limit (2) se aage"), 5)
        out = self.run_cli("run", "drama", "Moon Tales Season 2", "Dream Garden", "--dry-run", "--budget", "1")
        self.assertIn("time budget khatam", out)

    def test_missing_env_and_lock(self):
        os.environ.pop("AROLINKS_TOKEN")
        self.assertIn("Setup adhura hai: AROLINKS_TOKEN", self.run_cli("run", "drama", "Moon Tales Season 2"))
        os.environ["AROLINKS_TOKEN"] = "AROTOK"
        os.environ["DEVX_LOCK_WAIT"] = "0"
        with store.run_lock(1):
            self.assertIn("Dusra run chal raha hai", self.run_cli("run", "drama", "Moon Tales Season 2"))

    def test_shorten_failure_sends_nothing(self):
        for i in range(1, 4):
            self.state.short_fail.add(f"https://drive.google.com/file/d/ID{i}")
        self.assertIn("Links short nahi ho paye", self.run_cli("run", "drama", "Moon Tales Season 2"))
        self.assertEqual(self.state.tg_calls, [])

    def test_backup_source_and_auto_param_detection(self):
        self.write_profile(prof_json("primary", 10, "http://127.0.0.1:9"))        # dead entry
        self.write_profile(prof_json("backup", 20, self.base, mode="auto"))        # form says ?s= (ignored)
        out = self.run_cli("run", "drama", "Moon Tales Season 2")
        self.assertIn("✅ Post bhej diya: Moon Tales Season 2", out)

    def test_dead_sources_report_fetch_fail_without_browser(self):
        self.write_profile(prof_json("primary", 10, "http://127.0.0.1:9"))
        out = self.run_cli("run", "drama", "Moon Tales Season 2")
        self.assertIn("Primary source par issue hai", out)
        self.assertNotIn("Setup adhura", out)

    def test_poster_failure_dump_and_repair_marker(self):
        out = self.run_cli("run", "drama", "Bad Poster")
        self.assertIn("🔧 Bad Poster: Poster available nahi hai. [REPAIR source=primary dump=", out)
        dump = out.split("dump=")[1].split("]")[0]
        self.assertTrue((Path(dump) / "digest.txt").exists())
        self.assertEqual(self.state.tg_calls, [])

    def test_repair_flow_apply_then_rollback(self):
        out = self.run_cli("run", "drama", "Broken Layout")
        self.assertIn("Download links nahi mile", out)
        self.assertIn("[REPAIR source=primary", out)
        digest = (Path(out.split("dump=")[1].split("]")[0]) / "digest.txt").read_text()
        self.assertIn("Get 1", digest)
        cand = self.tmp / "cand.json"
        cand.write_text(json.dumps(prof_json("primary", 10, self.base, extra={
            "detail": {"links": {"container": ".downloads", "css": ["a.x"], "text_include": ""}}})))
        bad = self.tmp / "bad.json"
        bad.write_text(json.dumps(prof_json("primary", 10, self.base, extra={
            "detail": {"links": {"container": ".nothing-here"}}})))
        self.assertIn("REJECTED", self.run_cli("profile-apply", "drama", "primary", "--file", str(bad), "--title", "Broken Layout"))
        self.assertIn("APPLIED", self.run_cli("profile-apply", "drama", "primary", "--file", str(cand), "--title", "Broken Layout"))
        self.assertIn("origin=override", self.run_cli("profiles", "drama"))
        self.assertIn("✅ Post bhej diya: Broken Layout", self.run_cli("run", "drama", "Broken Layout"))
        # later the override rots: shipped profile still works for a normal drama -> auto rollback
        ov = Path(os.environ["DEVX_DATA_DIR"]) / "overrides" / "drama" / "primary.json"
        ov.write_text(json.dumps(prof_json("primary", 10, self.base, extra={
            "detail": {"links": {"css": ["a.nonexistent"]}}})))
        self.assertIn("✅ Post bhej diya: Moon Tales Season 2", self.run_cli("run", "drama", "Moon Tales Season 2"))
        self.assertFalse(ov.exists())                                    # moved to .history
        self.assertIn("origin=shipped", self.run_cli("profiles", "drama"))

    def test_token_never_in_logs_or_output(self):
        out = self.run_cli("run", "drama", "Moon Tales Season 2")
        log = (Path(os.environ["DEVX_DATA_DIR"]) / "logs" / "runs.log").read_text()
        for blob in (out, log):
            self.assertNotIn("AROTOK", blob)
            self.assertNotIn("TGTOK", blob)


if __name__ == "__main__":
    unittest.main()
