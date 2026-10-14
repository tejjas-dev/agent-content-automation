import json
import os
import unittest

from common import Base, ROOT, load

PAGE = """<html><head><title>My Demon (Korean Drama) Hindi Dubbed - KatDrama</title>
<meta property="og:image" content="http://image.tmdb.org/t/p/w500/my demon (poster).jpg">
<script>var x = "<a href='https://evil.test/skip'>no</a>";</script></head>
<body><h1>My Demon</h1>
<div class="info"><span class="info-label">Audio</span><span class="info-value">Hindi, Korean</span>
<span class="info-label">Episodes</span><span class="info-value">16</span>
<span class="info-label">Genres</span><span class="info-value">Action, Comedy</span></div>
<a href="/tag/korean">Korean</a>
<a href="https://facebook.com/share">480p share</a>
<a href="https://links.dramashindi.online/archives/11?utm_source=x&fbclid=abc#top">480p Single Episode</a>
<a href="https://links.dramashindi.online/archives/12">720p 10Bit Single Episode</a>
<a href="https://links.dramashindi.online/archives/12">720p duplicate</a>
<a href="https://links.dramashindi.online/archives/13">Click</a>
<p>padding padding padding padding padding padding padding padding padding padding padding padding padding padding</p>
</body></html>"""

SEARCH = """<html><body><h1>Search Results for "my demon"</h1>
<div class="card"><a href="/my-demon-2023-korean-drama-hindi-dubbed/"><img alt="x" src="/a.jpg">My Demon (2023) Korean Drama Hindi Dubbed</a></div>
<div class="card"><a href="/my-demon-2023-korean-drama-hindi-dubbed-2/"><h2>My Demon 2023 Hindi English Dual Audio</h2></a></div>
<div class="card"><a href="/my-demon-chinese-2018/">My Demon Chinese Drama 2018</a></div>
<a href="/category/korean/">Korean Dramas</a><a href="/page/2/">Next</a><a href="https://other.test/x">Other site drama</a>
<p>padding padding padding padding padding padding padding padding padding padding padding padding padding</p></body></html>"""


class TestDomains(Base):
    def d(self, *a):
        return self.out(load("drama-post", "drama").main, *a)

    def test_defaults_and_old_names(self):
        self.assertEqual(self.d("domain", "get", "primary")[1].strip(), "https://new.katdrama.my/")
        self.assertEqual(self.d("domain", "get", "fallback")[1].strip(), "https://katdrama.org/")
        self.assertEqual(self.d("domain", "get", "finder")[1].strip(), "https://katworld.net/?type=KatDrama")
        (self.root / "state" / "domains.json").write_text(json.dumps({"katdrama": "https://moved.example/"}))   # 0.3.x file
        self.assertEqual(self.d("domain", "get", "primary")[1].strip(), "https://moved.example/")
        self.assertEqual(self.d("domain", "get", "katdrama")[1].strip(), "https://moved.example/")

    def test_set_validates(self):
        for bad in ("http://x.example/", "https://127.0.0.1/", "https://localhost/", "https://user:pw@x.example/", "https://x.example:8443/", "javascript:1"):
            self.assertEqual(self.d("domain", "set", "primary", bad)[0], 2, bad)
        self.assertEqual(self.d("domain", "set", "fallback", "https://kd.example/")[0], 0)
        self.assertEqual(self.d("domain", "get", "fallback")[1].strip(), "https://kd.example/")
        self.assertEqual(self.d("domain", "get", "primary")[1].strip(), "https://new.katdrama.my/")

    def test_probe_states(self):
        m = load("drama-post", "drama")
        self.assertEqual(m.probe(self.base + "/ok")[0], "ok")
        self.assertEqual(m.probe(self.base + "/guard")[0], "ok")            # Cloudflare 403 = alive
        self.assertEqual(m.probe(self.base + "/nope")[0], "dead")           # 404
        st, final, _ = m.probe(self.base + "/hop")
        self.assertEqual(st, "moved"); self.assertIn("localhost", final)    # redirected to another host
        self.assertEqual(m.probe("http://127.0.0.1:9/", timeout=2)[0], "dead")

    def refresh(self, answers):
        m = load("drama-post", "drama")
        m.probe = lambda url, timeout=15: answers.get(url.rstrip("/"), ("dead", url, "DNS"))
        return m, self.out(m.main, "domain", "refresh")

    def test_refresh_primary_alive_changes_nothing(self):
        m, (rc, out) = self.refresh({"https://new.katdrama.my": ("ok", "https://new.katdrama.my/", "HTTP 200")})
        self.assertEqual(rc, 0); self.assertIn("DOMAIN_OK", out)
        self.assertFalse((self.root / "state" / "domains.json").exists())

    def test_refresh_follows_finder_when_primary_dead(self):
        m, (rc, out) = self.refresh({"https://katworld.net/?type=KatDrama": ("moved", "https://new2.katdrama.example/home", "HTTP 200"),
                                     "https://new2.katdrama.example": ("ok", "https://new2.katdrama.example/", "HTTP 200")})
        self.assertEqual(rc, 0); self.assertIn("DOMAIN_UPDATED primary https://new.katdrama.my/ -> https://new2.katdrama.example/", out)
        self.assertEqual(self.out(m.main, "domain", "get", "primary")[1].strip(), "https://new2.katdrama.example/")
        events = (self.root / "state" / "logs" / "events.jsonl").read_text()
        self.assertIn("DOMAIN_UPDATED", events)

    def test_refresh_follows_primary_redirect(self):
        m, (rc, out) = self.refresh({"https://new.katdrama.my": ("moved", "https://kd3.example/x", "HTTP 200"),
                                     "https://kd3.example": ("ok", "https://kd3.example/", "HTTP 200")})
        self.assertEqual(rc, 0); self.assertIn("-> https://kd3.example/", out)

    def test_refresh_refuses_bad_candidates(self):
        cases = {
            "finder does not redirect": {"https://katworld.net/?type=KatDrama": ("ok", "https://katworld.net/?type=KatDrama", "HTTP 200")},
            "finder dead": {},
            "candidate is an IP": {"https://katworld.net/?type=KatDrama": ("moved", "https://10.0.0.5/", "HTTP 200")},
            "candidate is plain http": {"https://katworld.net/?type=KatDrama": ("moved", "http://evil.example/", "HTTP 200")},
            "candidate is the finder host": {"https://katworld.net/?type=KatDrama": ("moved", "https://www.katworld.net/x", "HTTP 200")},
            "candidate unreachable": {"https://katworld.net/?type=KatDrama": ("moved", "https://down.example/", "HTTP 200")},
        }
        for name, answers in cases.items():
            m, (rc, out) = self.refresh(answers)
            self.assertEqual(rc, 1, name); self.assertIn("DOMAIN_REFRESH_FAILED", out, name)
            self.assertFalse((self.root / "state" / "domains.json").exists(), name)


class TestPick(Base):
    def setUp(self):
        super().setUp(); self.p = load("drama-find", "pick")

    def test_reading_audio(self):
        r = self.p.read_audio
        self.assertEqual(r("Hindi Dubbed"), ({"hindi"}, False))
        self.assertEqual(r("Hindi, Korean"), ({"hindi", "korean"}, True))
        self.assertEqual(r("Dual Audio [Hindi-English]")[0], {"hindi", "english"})
        self.assertEqual(r("Hindi Subs"), (set(), False))                       # subtitles are not audio
        self.assertEqual(r("Korean (Hindi Subs)")[0], {"korean"})
        self.assertEqual(r("Audio: Hindi + English | Subs: Korean")[0], {"hindi", "english"})
        self.assertEqual(r("Dual Audio"), (set(), True))
        self.assertEqual(r(None), (set(), False))

    def test_tiers_follow_the_owner_rule(self):
        t = lambda a: self.p.tier(a)[0]  # noqa: E731
        self.assertEqual([t("Hindi, Korean"), t("Hindi Dubbed"), t("English, Korean"), t("Korean"), t("Dual Audio"), t("")], [0, 1, 2, 3, 4, 4])
        self.assertLess(t("Hindi"), t("Korean, English, Thai"))                   # Hindi-only beats multi without Hindi
        self.assertLess(t("English"), t("Korean, Thai"))                          # no Hindi at all: English next

    def test_ranking_and_cli(self):
        c = [{"title": "a", "audio": "Korean"}, {"title": "b", "audio": "Hindi"}, {"title": "c", "audio": "Hindi, English"},
             {"title": "d", "audio": "Hindi, English, Korean"}, {"title": "e"}]
        self.assertEqual([r[2] for r in self.p.rank(c)], [4, 3, 2, 1, 5])         # more languages first inside a tier
        (self.task / "c.json").write_text(json.dumps(c))
        rc, out = self.out(self.p.main, str(self.task / "c.json"))
        self.assertEqual(rc, 0); self.assertIn("BEST 4", out); self.assertIn("candidates [5] have no audio", out)
        (self.task / "u.json").write_text(json.dumps([{"title": "x"}, {"title": "y", "audio": ""}]))
        self.assertIn("NEED_AUDIO 1 2", self.out(self.p.main, str(self.task / "u.json"))[1])
        self.assertEqual(self.out(self.p.main, str(self.task / "missing.json"))[0], 2)
        self.assertIn("tier=0", self.out(self.p.main, "--audio", "Hindi + Tamil")[1])


class TestExtract(Base):
    def setUp(self):
        super().setUp(); self.e = load("drama-scrape", "extract")

    def run_page(self, html, *extra):
        (self.task / "page.html").write_text(html, encoding="utf-8")
        return self.out(self.e.main, str(self.task / "page.html"), "--base", "https://site.test/my-demon/", "--write", str(self.task), *extra)

    def test_full_page_ok(self):
        rc, out = self.run_page(PAGE)
        self.assertEqual(rc, 0, out); self.assertTrue(out.startswith("EXTRACT OK"))
        data = json.loads((self.task / "data.json").read_text()); links = json.loads((self.task / "links.json").read_text())
        self.assertEqual({k: data[k] for k in ("title", "audio", "episodes", "genre")},
                         {"title": "My Demon", "audio": "Hindi, Korean", "episodes": "16", "genre": "Action, Comedy"})
        self.assertEqual(data["poster"], "https://image.tmdb.org/t/p/w500/my%20demon%20%28poster%29.jpg")   # https, %20, %28 %29
        self.assertEqual((data["page_url"], data["source"]), ("https://site.test/my-demon/", "site.test"))
        self.assertEqual([l["url"] for l in links], ["https://links.dramashindi.online/archives/11", "https://links.dramashindi.online/archives/12",
                                                      "https://links.dramashindi.online/archives/13"])        # tracking stripped, duplicate and social dropped
        self.assertEqual(links[0]["label"], "480p Single Episode"); self.assertEqual(links[2]["label"], "Click")  # hint host keeps unlabeled links
        self.assertTrue((self.task / "extract.json").exists())

    def test_partial_and_js_shell(self):
        rc, out = self.run_page("<html><head><title>Only Title - KatDrama</title></head><body><h1>Only Title</h1>" + "<p>text text text text text text</p>" * 12 + "</body></html>")
        self.assertEqual(rc, 1); self.assertIn("EXTRACT PARTIAL missing=poster,links", out)
        self.assertFalse((self.task / "links.json").exists())
        rc, out = self.run_page("<html><body><h1>Search Results</h1><p>Loading...</p></body></html>")
        self.assertEqual(rc, 1); self.assertIn("EXTRACT FAIL js_shell", out)
        self.assertEqual(self.out(self.e.main, str(self.task / "nope.html"), "--base", "https://a.test/")[1].strip(), "EXTRACT FAIL unreadable")

    def test_label_value_layouts(self):
        html = ("<html><body><dl><dt>Audio</dt><dd>Hindi</dd><dt>Episodes</dt><dd>8</dd></dl><table><tr><th>Genres:</th><td>Drama</td></tr></table>"
                "<p>Title: Moon Tales (Season 2)</p>" + "<p>filler filler filler filler filler</p>" * 12 + "</body></html>")
        d = self.e.extract(self._write(html), "https://s.test/a/")["data"]
        self.assertEqual((d["audio"], d["episodes"], d["genre"], d["title"]), ("Hindi", "8", "Drama", "Moon Tales Season 2"))

    def _write(self, html):
        p = self.task / "x.html"; p.write_text(html, encoding="utf-8"); return str(p)

    def test_clean_title(self):
        c = self.e.clean_title
        self.assertEqual(c("My Demon (Korean Drama) Hindi Dubbed - KatDrama"), "My Demon")
        self.assertEqual(c("Moon Tales (Season 2) [2024] Hindi Dubbed 720p"), "Moon Tales Season 2")
        self.assertEqual(c("Queen Of Tears | New Katdrama All Episodes"), "Queen Of Tears")
        self.assertEqual(c("Mr. Plankton - The Series"), "Mr. Plankton - The Series")        # a real hyphenated title survives

    def test_cards_mode_and_ranking_flow(self):
        (self.task / "s.html").write_text(SEARCH, encoding="utf-8")
        out_file = self.task / "cands.json"
        rc, out = self.out(self.e.main, "--cards", str(self.task / "s.html"), "--base", "https://site.test/?q=my%20demon", "--out", str(out_file))
        self.assertEqual(rc, 0, out)
        cands = json.loads(out_file.read_text())
        self.assertEqual(len(cands), 3)                                           # category, page and other-host links are not candidates
        self.assertEqual((cands[0]["year"], cands[0]["audio"]), ("2023", "Hindi"))
        self.assertEqual(cands[1]["audio"], "English, Hindi")
        best = load("drama-find", "pick").rank(cands)[0][3]
        self.assertIn("dubbed-2", best["url"])                                    # Hindi + English beats Hindi only
        rc, out = self.out(self.e.main, "--cards", str(self._write("<html><body><p>Loading...</p></body></html>")), "--base", "https://site.test/")
        self.assertEqual(rc, 1); self.assertIn("js_shell", out)

    def test_check_poster_falls_back_to_next_candidate(self):
        html = ('<html><head><meta property="og:image" content="https://img.test/missing.jpg"></head><body><h1>T</h1>'
                '<img class="poster" src="https://img.test/p.png"><a href="https://links.dramashindi.online/archives/1">480p Zip File</a>'
                + "<p>filler filler filler filler filler</p>" * 12 + "</body></html>")
        self.e.poster_ok = lambda u: u.endswith("/p.png")                           # first candidate is dead, second is a real image
        rc, out = self.run_page(html, "--check-poster")
        self.assertEqual(rc, 0, out); self.assertIn("poster=https://img.test/p.png", out)
        self.assertEqual(json.loads((self.task / "data.json").read_text())["poster"], "https://img.test/p.png")
        self.e.poster_ok = lambda u: False                                           # nothing usable -> PARTIAL, no data.json poster
        rc, out = self.run_page(html, "--check-poster")
        self.assertEqual(rc, 1); self.assertIn("missing=poster", out)

    def test_poster_real_check_on_local_server(self):
        self.assertTrue(self.e.poster_ok(self.base + "/p.png") is False)            # 67-byte test PNG is below the 100-byte sanity floor
        self.assertFalse(self.e.poster_ok(self.base + "/nope.png"))

    def test_hints_file_is_valid(self):
        h = json.loads((ROOT / "drama-scrape" / "references" / "hints.json").read_text())
        self.assertIn("dramashindi.online", h["link_hosts"]); self.assertIsInstance(h["skip_hosts"], list)


if __name__ == "__main__":
    unittest.main()
