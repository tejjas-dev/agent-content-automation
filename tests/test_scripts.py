import json
import os
import time
import unittest

from common import Base, S, caption, load, DATA


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




class TestCheckNormalization(Base):
    def test_brackets_in_title_and_trimmed_labels_are_not_false_failures(self):
        self.jwrite("data.json", {**DATA, "title": "My Demon [Hindi]"})
        self.jwrite("short.json", [{"label": "[480p] " + "x" * 60, "url": "u", "short": "https://arolinks.com/aaa"}])
        label = "(480p) " + "x" * 60
        cap = "📺 TITLE : My Demon (Hindi)\n🎙 AUDIO : Hindi Dubbed\n📺 EPISODES : 16\n🎭 GENRE : Action, Comedy\n\n" \
              f"📁 {label[:27]}… : https://arolinks.com/aaa\n\n"
        (self.task / "caption1.txt").write_text(cap, encoding="utf-8")
        self.assertEqual(load("drama-verify", "check").run(str(self.task), "my demon"), [])


class TestBuild(Base):
    def build(self):
        return self.out(load("drama-format", "build").main, "--task", str(self.task))

    def shorts(self, n, null=()):
        return [{"label": f"Episode {i} [720p]", "url": f"u{i}", "short": None if i in null else f"https://arolinks.com/{i:07d}"} for i in range(n)]

    def test_split_balanced_and_passes_checker(self):
        for n, want in ((5, [5]), (13, [7, 6]), (25, [9, 8, 8])):
            for f in self.task.glob("caption*.txt"):
                f.unlink()
            self.jwrite("data.json", DATA); self.jwrite("short.json", self.shorts(n))
            rc, out = self.build()
            caps = sorted(self.task.glob("caption*.txt"))
            self.assertEqual((rc, [c.read_text().count("📁") for c in caps]), (0, want), out)
            self.assertEqual(load("drama-verify", "check").run(str(self.task), "My Demon"), [])

    def test_null_entries_drop_their_tag_and_none_left_is_error(self):
        self.jwrite("data.json", DATA); self.jwrite("short.json", self.shorts(4, null=(1, 2)))
        rc, out = self.build()
        text = (self.task / "caption1.txt").read_text()
        self.assertEqual((rc, text.count("📁")), (0, 2)); self.assertIn("dropped 2", out)
        self.assertNotIn("Episode 1 ", text); self.assertNotIn("[", text)
        self.jwrite("short.json", self.shorts(2, null=(0, 1)))
        self.assertEqual(self.build()[0], 3)

    def test_long_labels_trimmed_and_missing_fields_omitted(self):
        self.jwrite("data.json", {"title": "T", "poster": "https://x/p.jpg", "audio": "Hindi"})
        self.jwrite("short.json", [{"label": "L" * 400, "url": "u", "short": "https://arolinks.com/a"}])
        self.assertEqual(self.build()[0], 0)
        t = (self.task / "caption1.txt").read_text()
        self.assertTrue(t.startswith("📺 TITLE : T\n🎙 AUDIO : Hindi\n\n📁 ")); self.assertNotIn("EPISODES", t)
        self.assertLessEqual(len(t.encode("utf-16-le")) // 2, 950)
        self.jwrite("data.json", {"title": "T" * 2000, "poster": "https://x/p.jpg"})
        self.assertEqual(self.build()[0], 4)
