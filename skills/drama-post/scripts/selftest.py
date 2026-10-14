#!/usr/bin/env python3
"""Offline smoke test of the pipeline scripts: no network, no Telegram, a temporary data folder. ~5 seconds.
Prints  SELFTEST OK n/n  or  SELFTEST FAIL <check>: <why>.  Exit 0 / 1.
It runs the scripts that sit next to it, so a draft overlay is tested exactly as it will run (proposal.py check uses it)."""
import atexit
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SK = Path(__file__).absolute().parents[2]
PAGE = """<html><head><title>My Demon (Korean Drama) Hindi Dubbed - KatDrama</title>
<meta property="og:image" content="https://image.tmdb.org/t/p/w500/abc.jpg"></head><body><h1>My Demon</h1>
<span class="info-label">Audio</span><span class="info-value">Hindi, Korean</span>
<span class="info-label">Episodes</span><span class="info-value">16</span>
<span class="info-label">Genres</span><span class="info-value">Action, Comedy</span>
<a href="https://links.dramashindi.online/archives/11">480p Single Episode</a>
<a href="https://links.dramashindi.online/archives/12">720p Zip File</a>
<p>padding padding padding padding padding padding padding padding padding padding padding padding padding padding padding</p>
</body></html>"""


def main():
    tmp = Path(tempfile.mkdtemp(prefix="devx-selftest-"))
    atexit.register(shutil.rmtree, tmp, True)
    env = {**os.environ, "DEVX_DATA_DIR": str(tmp / "data"), "TELEGRAM_BOT_TOKEN": "", "DEVX_BACKOFF": "0"}
    env.pop("DEVX_SKILLS_DIR", None)

    def run(script, *args, e=None):
        p = subprocess.run([sys.executable, str(SK / script), *args], capture_output=True, text=True, timeout=60, env=e or env)
        return p.returncode, (p.stdout + p.stderr).strip()

    checks, task = [], None

    def compiles():
        for f in sorted(SK.glob("*/scripts/*.py")):
            compile(f.read_text(encoding="utf-8"), str(f), "exec")

    def queue_task_step():
        nonlocal task
        assert "RUNNER" in run("drama-post/scripts/drama.py", "enqueue", "Selftest A")[1]
        assert run("drama-post/scripts/drama.py", "next")[1] == "Selftest A"
        task = Path(run("drama-post/scripts/drama.py", "task", "Selftest A")[1])
        assert run("drama-post/scripts/drama.py", "step", str(task))[1] == "STEP FIND"
        (task / "find.txt").write_text("source=primary\n", encoding="utf-8")
        assert run("drama-post/scripts/drama.py", "step", str(task))[1] == "STEP SCRAPE"

    def extract():
        (task / "page.html").write_text(PAGE, encoding="utf-8")
        rc, out = run("drama-scrape/scripts/extract.py", str(task / "page.html"), "--base", "https://site.test/my-demon/", "--write", str(task))
        assert rc == 0 and out.startswith("EXTRACT OK") and "title='My Demon'" in out, out
        assert len(json.loads((task / "links.json").read_text(encoding="utf-8"))) == 2

    def pick():
        c = [{"title": "a", "audio": "Korean"}, {"title": "b", "audio": "Hindi"}, {"title": "c", "audio": "Hindi, Korean"}]
        (task / "cands.json").write_text(json.dumps(c), encoding="utf-8")
        rc, out = run("drama-find/scripts/pick.py", str(task / "cands.json"))
        assert rc == 0 and "BEST 3" in out, out

    def short_build_verify_dry():
        data = json.loads((task / "data.json").read_text(encoding="utf-8"))
        data["poster"] = "https://img.test/p.jpg"
        (task / "data.json").write_text(json.dumps(data), encoding="utf-8")
        links = json.loads((task / "links.json").read_text(encoding="utf-8"))
        (task / "short.json").write_text(json.dumps([{**l, "short": f"https://arolinks.com/t{i}"} for i, l in enumerate(links)]), encoding="utf-8")
        assert run("drama-post/scripts/drama.py", "step", str(task))[1] == "STEP PUBLISH"
        rc, out = run("drama-post/scripts/publish.py", "--task", str(task), "--title", "My Demon", "--dry-run")
        assert rc == 0 and "REPLY (dry-run)" in out, out

    def send_needs_token():
        rc, out = run("telegram-send/scripts/send.py", "--task", str(task))
        assert rc == 2 and "TELEGRAM_BOT_TOKEN" in out, out

    for fn in (compiles, queue_task_step, extract, pick, short_build_verify_dry, send_needs_token):
        checks.append(fn)
    for n, fn in enumerate(checks, 1):
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            print(f"SELFTEST FAIL {fn.__name__}: {type(e).__name__} {str(e)[:160]}")
            return 1
    print(f"SELFTEST OK {len(checks)}/{len(checks)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
