#!/usr/bin/env python3
"""build -> verify -> send in ONE call.   publish.py --task DIR --title "<requested title>" [--force] [--dry-run]
Prints progress lines and a final line:  REPLY <the Hinglish line to tell the user>
On a build/verify problem it stops and lists the problems (nothing is sent, the task is marked .failed so the next try scrapes fresh).
--dry-run = build + verify only: nothing is sent, nothing is written to the ledger (safe test on the real server).
Exit 0 only when everything was sent (or the dry run is ready). Sub-scripts come from the draft-aware skills view when drafts are READY."""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).absolute().parent
SK = HERE.parents[1]
try:
    sys.path.insert(0, str(HERE))
    import proposal
    SK = Path(proposal.effective(SK))
except Exception:  # noqa: BLE001  drafts are optional: main skills are used
    pass


def log_event(task, code, detail=""):
    try:
        t = Path(task).resolve()
        root = t.parents[1] if t.parent.name == "work" else None
        if root is None:
            return
        d = root / "state" / "logs"
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "events.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": int(time.time()), "stage": "publish", "code": code, "task": t.name, "detail": detail[:200]}, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        pass


def run(script, *args, timeout=120):
    try:
        p = subprocess.run([sys.executable, str(SK / script), *args], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, f"timeout after {timeout}s"
    except OSError as e:
        return 125, f"cannot run {script}: {type(e).__name__}"
    return p.returncode, (p.stdout + p.stderr).strip()


def mark(task, name):
    try:
        Path(task, name).touch()
    except OSError:
        pass


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    try:
        with open(os.path.join(a.task, "data.json"), encoding="utf-8") as fh:
            title = json.load(fh).get("title") or a.title
    except Exception:  # noqa: BLE001
        title = a.title
    rc, out = run("drama-format/scripts/build.py", "--task", a.task)
    print("BUILD " + out)
    if rc == 3:
        mark(a.task, ".failed")
        log_event(a.task, "NO_LINKS", out)
        print("REPLY Links short nahi ho paye.")
        return 1
    if rc:
        mark(a.task, ".failed")
        log_event(a.task, "BUILD_FAIL", out)
        print(f"REPLY Post format nahi ban paya: {out.split(' ', 1)[-1][:80]}.")
        return 1
    rc, out = run("drama-verify/scripts/check.py", "--task", a.task, "--title", a.title)
    print("VERIFY " + out)
    if rc:
        mark(a.task, ".failed")
        first = next((l[2:] for l in out.splitlines() if l.startswith("- ")), "check failed")
        log_event(a.task, "VERIFY_FAIL", first)
        print("-> fix only the listed problems (skills drama-format / drama-verify), run publish.py once more")
        print(f"REPLY Post format nahi ban paya: {first}.")
        return 1
    if a.dry_run:
        n = len([f for f in os.listdir(a.task) if re.fullmatch(r"caption\d+\.txt", f)])
        print(f"REPLY (dry-run) Post ready: {title} -> {n} post(s). Verify PASS, kuch send nahi kiya.")
        return 0
    rc, out = run("telegram-send/scripts/send.py", "--task", a.task, *(["--force"] if a.force else []), timeout=1500)
    print("SEND " + out)
    if rc == 124:
        log_event(a.task, "SEND_TIMEOUT", out)
        print("REPLY Channel me post send timeout hua (post chala gaya ho sakta hai): channel check karke batao, tab dobara chalaunga.")
        return 1
    m = re.search(r"ok=(\d+) fail=(\d+) channels=(\d+) posts=(\d+)", out)
    if not m:
        log_event(a.task, "SEND_ERROR", out.splitlines()[-1] if out else "unknown")
        print(f"REPLY Channel me post send nahi ho paya: {out.splitlines()[-1][:80] if out else 'unknown'}.")
        return 1
    ok, fail, chans, posts = map(int, m.groups())
    skipped = sum(1 for l in out.splitlines() if l.startswith("SKIP"))
    if not fail:
        mark(a.task, ".done")
        log_event(a.task, "OK", f"{title} ch={chans} posts={posts} skipped={skipped}")
        if skipped == chans * posts:
            print(f"REPLY ℹ️ {title}: ye task pehle hi bhej diya tha, is baar kuch naya nahi gaya (dobara bhejna ho to --force).")
        else:
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
