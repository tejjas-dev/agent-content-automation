#!/usr/bin/env python3
"""build -> verify -> send in ONE call.   publish.py --task DIR --title "<requested title>" [--force]
Prints progress lines and a final line:  REPLY <the Hinglish line to tell the user>
On a verify problem it stops and lists the problems (nothing is sent). Exit 0 only when everything was sent."""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SK = Path(__file__).resolve().parents[2]


def run(script, *args):
    p = subprocess.run([sys.executable, str(SK / script), *args], capture_output=True, text=True, timeout=1500)
    return p.returncode, (p.stdout + p.stderr).strip()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    try:
        title = json.load(open(os.path.join(a.task, "data.json"), encoding="utf-8")).get("title") or a.title
    except Exception:  # noqa: BLE001
        title = a.title
    rc, out = run("drama-format/scripts/build.py", "--task", a.task)
    print("BUILD " + out)
    if rc == 3:
        print("REPLY Links short nahi ho paye.")
        return 1
    if rc:
        print(f"REPLY Post format nahi ban paya: {out.split(' ', 1)[-1][:80]}.")
        return 1
    rc, out = run("drama-verify/scripts/check.py", "--task", a.task, "--title", a.title)
    print("VERIFY " + out)
    if rc:
        first = next((l[2:] for l in out.splitlines() if l.startswith("- ")), "check failed")
        print("-> fix only the listed problems (skills drama-format / drama-verify), run publish.py once more")
        print(f"REPLY Post format nahi ban paya: {first}.")
        return 1
    rc, out = run("telegram-send/scripts/send.py", "--task", a.task, *(["--force"] if a.force else []))
    print("SEND " + out)
    m = re.search(r"ok=(\d+) fail=(\d+) channels=(\d+) posts=(\d+)", out)
    if not m:
        print(f"REPLY Channel me post send nahi ho paya: {out.splitlines()[-1][:80] if out else 'unknown'}.")
        return 1
    ok, fail, chans, posts = map(int, m.groups())
    if not fail:
        print(f"REPLY ✅ Post bhej diya: {title} → {chans} channel(s), {posts} post(s).")
        return 0
    first = next((l for l in out.splitlines() if l.startswith("FAIL")), "FAIL ? ? unknown").split(" ", 3)
    why = f"{first[1]} — {first[3] if len(first) > 3 else 'unknown'}"
    if ok == 0:
        print(f"REPLY Channel me post send nahi ho paya: {why}.")
    else:
        print(f"REPLY ⚠️ {title}: {ok}/{chans * posts} post gaye. Fail: {why}.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
