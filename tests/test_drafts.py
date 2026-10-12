"""Draft (self-improvement) flow: new/add/check -> READY overlay -> approve/reject, patch file, rollback, install/setup/doctor.
Every test works on a COPY of the skills folder, so the real repo is never touched."""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from common import Base, ROOT, load

HINTS = "drama-scrape/references/hints.json"
EXTRA_PAGE = ("<html><head><title>My Demon (Korean Drama) - KatDrama</title></head><body><h1>My Demon</h1>"
              '<a href="https://files.newhost.example/a1">Get it</a>' + "<p>padding padding padding padding</p>" * 6 + "</body></html>")


class DraftBase(Base):
    def setUp(self):
        super().setUp()
        self.sk = self.tmp / "sk"
        shutil.copytree(ROOT, self.sk, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        spec = importlib.util.spec_from_file_location("proposal_copy", self.sk / "drama-post" / "scripts" / "proposal.py")
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.state = self.root / "state"

    def P(self, *args):
        return self.out(self.m.main, *args)

    def sub(self, script, *args):
        p = subprocess.run([sys.executable, str(self.sk / script), *args], capture_output=True, text=True, timeout=120)
        return p.returncode, (p.stdout + p.stderr).strip()

    def new(self, title="Fix link hosts", note="use the new link host rule"):
        rc, out = self.P("new", title, "--why", "site changed", "--note", note)
        self.assertEqual(rc, 0, out)
        return out.strip()

    def dfile(self, i, rel):
        return self.state / "draft" / i / "files" / rel

    def add_hint_draft(self, host="newhost.example", **kw):
        i = self.new(**kw)
        rc, out = self.P("add", i, HINTS)
        self.assertEqual(rc, 0, out)
        p = self.dfile(i, HINTS)
        h = json.loads(p.read_text(encoding="utf-8"))
        h["link_hosts"].append(host)
        p.write_text(json.dumps(h), encoding="utf-8")
        return i

    def env(self):
        rc, out = self.sub("drama-post/scripts/drama.py", "env")
        self.assertEqual(rc, 0, out)
        return dict(l.split("=", 1) for l in out.splitlines() if "=" in l)

    def main_text(self, rel):
        return (self.sk / rel).read_text(encoding="utf-8")


class TestDraftLifecycle(DraftBase):
    def test_new_dedupes_by_title_and_limits_open_drafts(self):
        i = self.new("Fix Link Hosts")
        self.assertRegex(i, r"^d\d{8}-\d{6}-[a-z0-9-]+$")
        self.assertEqual(self.P("new", "fix link-hosts!", "--why", "again")[1].strip(), f"DRAFT_EXISTS {i}")
        for n in range(4):
            self.new(f"another {n}")
        rc, out = self.P("new", "one too many", "--why", "x")
        self.assertEqual(rc, 2); self.assertIn("DRAFT_LIMIT", out)

    def test_add_refuses_unsafe_or_unknown_paths(self):
        i = self.new()
        for bad in ("../x.py", "/etc/passwd", "drama-post/../../x.py", "drama-post/.hidden.py", "nope/scripts/a.py",
                    "drama-post/scripts/a.exe", "a.py", "drama-post/a/b/c/d.py", ".git/config"):
            rc, out = self.P("add", i, bad)
            self.assertEqual(rc, 2, bad); self.assertIn("ERROR", out)
        self.assertEqual(self.P("add", i, "drama-post/scripts/helper.py")[0], 0)        # a NEW file is fine
        self.assertEqual((self.state / "draft" / i / "files" / "drama-post" / "scripts" / "helper.py").read_text(), "")

    def test_bad_ids_are_rejected_before_touching_the_disk(self):
        for cmd in ("show", "check", "reject"):
            rc, out = self.P(cmd, "../../etc")
            self.assertEqual(rc, 2); self.assertIn("bad draft id", out)
        self.assertEqual(self.P("show", "d20200101-000000-nothing")[0], 2)

    def test_check_syntax_error_fails_and_fix_makes_it_ready(self):
        i = self.new("Fix pick")
        p = Path(self.P("add", i, "drama-find/scripts/pick.py")[1].strip())
        good = p.read_text(encoding="utf-8")
        p.write_text(good + "\ndef broken(:\n", encoding="utf-8")
        rc, out = self.P("check", i)
        self.assertEqual(rc, 1); self.assertIn("FAILED", out); self.assertIn("SyntaxError", out)
        p.write_text(good + "\n# harmless\n", encoding="utf-8")
        rc, out = self.P("check", i)
        self.assertEqual(rc, 0, out); self.assertIn("READY", out); self.assertIn("SELFTEST OK", out)
        self.assertEqual(self.main_text("drama-find/scripts/pick.py"), good)            # main untouched

    def test_invalid_json_and_empty_draft_fail(self):
        i = self.new()
        self.assertIn("no files", self.P("check", i)[1])
        self.P("add", i, HINTS)
        self.dfile(i, HINTS).write_text("{not json", encoding="utf-8")
        rc, out = self.P("check", i)
        self.assertEqual(rc, 1); self.assertIn("FAILED", out)

    def test_selftest_failure_in_overlay_blocks_ready(self):
        i = self.new("Break extract")
        p = Path(self.P("add", i, "drama-scrape/scripts/extract.py")[1].strip())
        p.write_text(p.read_text(encoding="utf-8").replace("EXTRACT OK", "EXTRACT FINE"), encoding="utf-8")
        rc, out = self.P("check", i)
        self.assertEqual(rc, 1); self.assertIn("FAILED", out); self.assertIn("SELFTEST FAIL", out)
        self.assertNotIn(i, self.env().get("NOTES", ""))
        self.assertEqual(self.env()["SK"], str(self.sk))                                # failed draft never becomes active

    def test_reject_removes_draft_and_overlay(self):
        i = self.add_hint_draft()
        self.assertEqual(self.P("check", i)[0], 0)
        self.assertIn(str(self.state / "view"), self.env()["SK"])
        self.assertIn("REJECTED", self.P("reject", i)[1])
        self.assertEqual(self.P("list")[1].strip(), "NO_DRAFTS")
        e = self.env()
        self.assertEqual(e["SK"], str(self.sk)); self.assertNotIn("DRAFTS", e); self.assertNotIn("NOTES", e)
        self.assertFalse((self.state / "draft" / "active.md").exists())

    def test_show_prints_a_git_style_diff(self):
        i = self.add_hint_draft()
        rc, out = self.P("show", i)
        self.assertEqual(rc, 0)
        self.assertIn("--- a/skills/" + HINTS, out); self.assertIn("+++ b/skills/" + HINTS, out); self.assertIn("newhost.example", out)

    def test_two_ready_drafts_cannot_touch_the_same_file(self):
        a = self.add_hint_draft("one.example", title="first", note="n1")
        self.assertEqual(self.P("check", a)[0], 0)
        b = self.add_hint_draft("two.example", title="second", note="n2")
        rc, out = self.P("check", b)
        self.assertEqual(rc, 1); self.assertIn("also changed by READY draft", out)


class TestOverlay(DraftBase):
    def test_ready_draft_is_used_by_later_runs_and_main_stays_untouched(self):
        before = self.main_text(HINTS)
        i = self.add_hint_draft(note="trust files.newhost.example links")
        rc, out = self.P("check", i)
        self.assertEqual(rc, 0, out)
        e = self.env()
        view = Path(e["SK"])
        self.assertEqual(view.parent, self.state / "view")
        self.assertIn("1 ready", e["DRAFTS"])
        self.assertIn(i, Path(e["NOTES"]).read_text(encoding="utf-8")); self.assertIn("trust files.newhost.example", Path(e["NOTES"]).read_text(encoding="utf-8"))
        # draft file copied (real file), everything else is a symlink to main
        self.assertFalse((view / HINTS).is_symlink()); self.assertIn("newhost.example", (view / HINTS).read_text(encoding="utf-8"))
        fetch = view / "drama-scrape" / "scripts" / "fetch.py"
        self.assertTrue(fetch.is_symlink()); self.assertEqual(os.path.realpath(fetch), os.path.realpath(self.sk / "drama-scrape" / "scripts" / "fetch.py"))
        self.assertEqual((view / ".main").read_text(encoding="utf-8"), str(self.sk))
        self.assertEqual(self.main_text(HINTS), before)                                  # MAIN NOT CHANGED
        # same view is reused, not rebuilt on every run
        self.assertEqual(self.env()["SK"], e["SK"])

    def test_extract_from_the_view_uses_the_draft_hint_but_main_does_not(self):
        page = self.task / "page.html"
        page.write_text(EXTRA_PAGE, encoding="utf-8")
        i = self.add_hint_draft()
        self.assertEqual(self.P("check", i)[0], 0)
        view = self.env()["SK"]
        args = [str(page), "--base", "https://site.test/my-demon/"]
        rc_main, out_main = self.sub("drama-scrape/scripts/extract.py", *args)
        p = subprocess.run([sys.executable, str(Path(view) / "drama-scrape" / "scripts" / "extract.py"), *args], capture_output=True, text=True)
        self.assertNotIn("links=1", out_main, out_main)                                  # main: host not trusted -> no link
        self.assertIn("links=1", p.stdout + p.stderr, p.stdout + p.stderr)               # draft view: host trusted

    def test_modifying_a_ready_draft_deactivates_it_until_checked_again(self):
        i = self.add_hint_draft()
        self.assertEqual(self.P("check", i)[0], 0)
        h = json.loads(self.dfile(i, HINTS).read_text(encoding="utf-8")); h["link_hosts"].append("sneaky.example")
        self.dfile(i, HINTS).write_text(json.dumps(h), encoding="utf-8")                 # edited AFTER the test passed
        e = self.env()
        self.assertEqual(e["SK"], str(self.sk)); self.assertIn("0 ready, 1 other", e["DRAFTS"]); self.assertNotIn("NOTES", e)
        self.assertEqual(self.P("list")[1].split()[1], "draft")
        self.assertEqual(self.P("check", i)[0], 0)
        self.assertIn("1 ready", self.env()["DRAFTS"])

    def test_publish_runs_sub_scripts_from_the_view(self):
        i = self.new("Verify marker")
        p = Path(self.P("add", i, "drama-verify/scripts/check.py")[1].strip())
        t = p.read_text(encoding="utf-8")
        marker = 'if __name__ == "__main__":\n'
        self.assertIn(marker, t)
        p.write_text(t.replace(marker, marker + '    print("DRAFT_MARK")\n'), encoding="utf-8")
        self.assertEqual(self.P("check", i)[0], 0)
        task = self.root / "work" / "pt"
        task.mkdir(parents=True)
        (task / "data.json").write_text(json.dumps({"title": "My Demon", "audio": "Hindi Dubbed", "episodes": "16", "genre": "Action",
                                                    "poster": "https://127.0.0.1:1/p.png"}), encoding="utf-8")
        (task / "short.json").write_text(json.dumps([{"label": "480p Single Episode", "url": "u", "short": "https://arolinks.com/0000001"}]), encoding="utf-8")
        rc, out = self.sub("drama-post/scripts/publish.py", "--task", str(task), "--title", "my demon", "--dry-run")
        self.assertEqual(rc, 0, out); self.assertIn("DRAFT_MARK", out)
        self.P("reject", i)
        rc, out = self.sub("drama-post/scripts/publish.py", "--task", str(task), "--title", "my demon", "--dry-run")
        self.assertEqual(rc, 0, out); self.assertNotIn("DRAFT_MARK", out)

    def test_draft_goes_stale_when_main_changes_after_a_plugin_update(self):
        i = self.add_hint_draft()
        self.assertEqual(self.P("check", i)[0], 0)
        self.assertIn(str(self.state / "view"), self.env()["SK"])
        h = json.loads(self.main_text(HINTS)); h["link_hosts"].append("upstream.example")             # install.sh brought a newer main file
        (self.sk / HINTS).write_text(json.dumps(h), encoding="utf-8")
        e = self.env()
        self.assertEqual(e["SK"], str(self.sk))                                                      # the old-based draft no longer shadows it
        self.assertEqual(self.P("list")[1].split()[1], "stale")
        rc, out = self.P("check", i)
        self.assertEqual(rc, 1); self.assertIn("STALE", out)
        rc, out = self.P("approve", i, "--user-approved")
        self.assertEqual(rc, 1); self.assertIn("APPROVE_REFUSED", out)
        self.assertIn("upstream.example", self.main_text(HINTS)); self.assertNotIn("newhost.example", self.main_text(HINTS))

    def test_draft_adding_a_new_file_goes_stale_if_main_gets_that_file(self):
        i = self.new("New file")
        Path(self.P("add", i, "drama-post/references/extra-note.md")[1].strip()).write_text("mine\n", encoding="utf-8")
        self.assertEqual(self.P("check", i)[0], 0)
        (self.sk / "drama-post/references/extra-note.md").write_text("upstream\n", encoding="utf-8")
        self.assertEqual(self.env()["SK"], str(self.sk)); self.assertIn("STALE", self.P("check", i)[1])

    def test_view_in_use_is_touched_so_cleanup_never_removes_it_mid_run(self):
        i = self.add_hint_draft()
        self.assertEqual(self.P("check", i)[0], 0)
        view = Path(self.env()["SK"])
        os.utime(view, (1, 1))                                                                       # looks 50 years old
        self.assertEqual(self.env()["SK"], str(view))
        self.assertGreater(view.stat().st_mtime, 1_000_000)

    def test_same_second_same_slug_never_share_a_draft_folder(self):
        long = "x" * 40
        a = self.new(long + " first"); b = self.new(long + " second")
        self.assertNotEqual(a, b); self.assertEqual(len(self.P("list")[1].strip().splitlines()), 2)

    def test_status_mentions_open_drafts(self):
        i = self.add_hint_draft()
        self.P("check", i)
        rc, out = self.sub("drama-post/scripts/drama.py", "status")
        self.assertEqual(rc, 0); self.assertIn("draft", out.lower())


class TestApprove(DraftBase):
    def test_approve_needs_the_owner_flag(self):
        i = self.add_hint_draft()
        before = self.main_text(HINTS)
        rc, out = self.P("approve", i)
        self.assertEqual(rc, 2); self.assertIn("--user-approved", out)
        self.assertEqual(self.main_text(HINTS), before); self.assertTrue((self.state / "draft" / i).is_dir())

    def test_approve_applies_backs_up_writes_patch_and_cleans_the_draft(self):
        before = self.main_text(HINTS)
        i = self.add_hint_draft()
        new = self.P("add", i, "drama-post/references/extra-note.md")[1].strip()
        Path(new).write_text("# note\nnew file in the draft\n", encoding="utf-8")
        rc, out = self.P("approve", i, "--user-approved")
        self.assertEqual(rc, 0, out); self.assertIn("APPROVED", out)
        self.assertIn("newhost.example", self.main_text(HINTS))
        self.assertEqual(self.main_text("drama-post/references/extra-note.md"), "# note\nnew file in the draft\n")
        self.assertEqual((self.state / "backup" / i / HINTS).read_text(encoding="utf-8"), before)
        patch = (self.state / "patches" / f"{i}.patch").read_text(encoding="utf-8")
        self.assertIn("--- a/skills/" + HINTS, patch); self.assertIn("--- /dev/null", patch); self.assertIn("+++ b/skills/drama-post/references/extra-note.md", patch)
        self.assertFalse((self.state / "draft" / i).exists())                            # draft cleaned
        self.assertEqual(self.P("list")[1].strip(), "NO_DRAFTS")
        e = self.env()
        self.assertEqual(e["SK"], str(self.sk)); self.assertNotIn("DRAFTS", e)           # back to the plain main skills

    @unittest.skipUnless(shutil.which("git"), "git not installed")
    def test_patch_applies_to_the_original_repo_with_git_apply(self):
        repo = self.tmp / "repo"
        shutil.copytree(self.sk, repo / "skills")
        git = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=repo, capture_output=True, text=True)  # noqa: E731
        git("init", "-q"); git("add", "-A"); self.assertEqual(git("commit", "-qm", "base").returncode, 0)
        i = self.add_hint_draft()
        Path(self.P("add", i, "drama-post/references/extra-note.md")[1].strip()).write_text("hello\n", encoding="utf-8")
        self.assertEqual(self.P("approve", i, "--user-approved")[0], 0)
        patch = self.state / "patches" / f"{i}.patch"
        r = git("apply", "--check", str(patch))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(git("apply", str(patch)).returncode, 0)
        self.assertEqual((repo / "skills" / HINTS).read_text(encoding="utf-8"), self.main_text(HINTS))
        self.assertEqual((repo / "skills/drama-post/references/extra-note.md").read_text(encoding="utf-8"), "hello\n")

    def test_failing_selftest_after_apply_rolls_back_everything(self):
        before = self.main_text(HINTS)
        i = self.add_hint_draft()
        Path(self.P("add", i, "drama-post/references/extra-note.md")[1].strip()).write_text("x\n", encoding="utf-8")
        self.assertEqual(self.P("check", i)[0], 0)
        with mock.patch.object(self.m, "run_selftest", side_effect=[(True, "ok"), (False, "boom")]):    # check passes, main run fails
            rc, out = self.P("approve", i, "--user-approved")
        self.assertEqual(rc, 1); self.assertIn("APPROVE_FAILED", out); self.assertIn("boom", out)
        self.assertEqual(self.main_text(HINTS), before)
        self.assertFalse((self.sk / "drama-post/references/extra-note.md").exists())
        self.assertEqual(list((self.state / "patches").glob("*.patch")) if (self.state / "patches").exists() else [], [])
        self.assertEqual(self.P("list")[1].split()[1], "failed")

    def test_failed_copy_leaves_no_new_file_behind(self):
        i = self.add_hint_draft()
        self.assertEqual(self.P("check", i)[0], 0)
        with mock.patch.object(self.m.shutil, "copy2", side_effect=OSError("disk full")):
            rc, out = self.P("approve", i, "--user-approved")
        self.assertEqual(rc, 1); self.assertIn("APPROVE_FAILED", out)
        self.assertEqual(list(self.sk.rglob("*.new")), [])

    def test_approve_refused_when_the_draft_tests_fail(self):
        i = self.new("Broken")
        p = Path(self.P("add", i, "drama-find/scripts/pick.py")[1].strip())
        original = p.read_text(encoding="utf-8")
        p.write_text(original + "\ndef broken(:\n", encoding="utf-8")
        rc, out = self.P("approve", i, "--user-approved")
        self.assertEqual(rc, 1); self.assertIn("APPROVE_REFUSED", out)
        self.assertEqual(self.main_text("drama-find/scripts/pick.py"), original)

    def test_approve_cli_end_to_end_with_real_selftest(self):
        i = self.add_hint_draft()
        rc, out = self.sub("drama-post/scripts/proposal.py", "approve", i, "--user-approved")
        self.assertEqual(rc, 0, out); self.assertIn("APPROVED", out)
        self.assertIn("newhost.example", self.main_text(HINTS))
        self.assertTrue(list((self.state / "patches").glob("*.patch")))


class TestSetupFiles(Base):
    def test_install_copies_swaps_and_leaves_no_temp_folder(self):
        dest = self.tmp / "agent-skills"
        repo = Path(ROOT).parent
        r = subprocess.run(["sh", str(repo / "install.sh"), str(dest)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((dest / "drama-post" / "SKILL.md").is_file())
        self.assertEqual(sorted(p.name for p in dest.iterdir() if p.name.startswith(".")), [])       # no .name.new left
        (dest / "drama-post" / "stale.txt").write_text("old", encoding="utf-8")
        self.assertEqual(subprocess.run(["sh", str(repo / "install.sh"), str(dest)], capture_output=True, text=True).returncode, 0)
        self.assertFalse((dest / "drama-post" / "stale.txt").exists())                              # re-install = clean swap
        link = self.tmp / "linked"
        self.assertEqual(subprocess.run(["sh", str(repo / "install.sh"), str(link), "--link"], capture_output=True, text=True).returncode, 0)
        self.assertTrue((link / "drama-post").is_symlink())

    def test_setup_pins_scrapling(self):
        t = (Path(ROOT) / "drama-post/scripts/setup.sh").read_text(encoding="utf-8")
        self.assertIn("0.4.15", t); self.assertRegex(t, r'scrapling\[fetchers\]==\$V'); self.assertNotIn(" -U", t)

    def test_doctor_warns_about_whitespace_in_secrets_and_bad_channel_ids(self):
        os.environ["TELEGRAM_BOT_TOKEN"] = " 123:abc\n"
        os.environ["DRAMA_POST_CHANNEL_IDS"] = "-100123, not-an-id"
        p = subprocess.run([sys.executable, str(Path(ROOT) / "drama-post/scripts/doctor.py")], capture_output=True, text=True, timeout=60)
        out = p.stdout + p.stderr
        self.assertNotIn("123:abc", out)                                                            # secrets never printed
        self.assertRegex(out.lower(), r"whitespace|space")
        self.assertRegex(out.lower(), r"channel")

    def test_manifest_versions_match(self):
        repo = Path(ROOT).parent
        v = {json.loads((repo / f).read_text(encoding="utf-8"))["version"] for f in (".claude-plugin/plugin.json", "gemini-extension.json")}
        self.assertEqual(len(v), 1)
        self.assertRegex((repo / "plugin.yaml").read_text(encoding="utf-8"), r"version:\s*['\"]?" + re.escape(v.pop()))


if __name__ == "__main__":
    unittest.main()
