#!/usr/bin/env python3
"""Cleanup of a content type's temporary data (cron friendly, no AI, no tokens).
  cleanup.py [--type drama] [--hours 24] [--dry-run] [--force] [--quiet] [--no-browser-temp]

DATA = $DEVX_DATA_DIR, else /workspace if writable, else ~/.devx-content.   Target = DATA/<type>/
Removes everything in it except state/: work/<task> folders (page.html, extracts, captions ...) and any stray file/folder older
than --hours (default 24, so a run in progress is never hit). Then state/ housekeeping (only these, never queue/ledger/notes/domains):
  logs/events.jsonl lines > 7 days, queue.jsonl.bad > 7 days, view/* > --hours, backup/* > 7 days, patches/* > 30 days,
  FAILED drafts > 3 days. posted.jsonl lines older than DEVX_LEDGER_DAYS (default 30) are trimmed.
Also removes leftover browser temp folders of the scraping engine in the system temp dir (playwright_*, .org.chromium.*) older than --hours
unless --no-browser-temp. With --hours < 1 and a live runner it refuses unless --force."""
import argparse
import glob
import json
import os
import re
import shutil
import sys
import tempfile
import time

BROWSER_TEMP = ("playwright_chromiumdev_profile-*", "playwright-artifacts-*", "playwright_firefoxdev_profile-*", ".org.chromium.Chromium.*", "rust_mozprofile*")


def data_dir():
    e = os.environ.get("DEVX_DATA_DIR")
    if e:
        return e
    return "/workspace" if os.path.isdir("/workspace") and os.access("/workspace", os.W_OK) else os.path.join(os.path.expanduser("~"), ".devx-content")


def newest(p):
    try:
        return max([os.path.getmtime(p)] + [os.path.getmtime(os.path.join(r, f)) for r, _, fs in os.walk(p) for f in fs])
    except OSError:
        return 0


def rm(p, dry):
    if dry:
        return
    if os.path.isdir(p) and not os.path.islink(p):
        shutil.rmtree(p, ignore_errors=True)
    else:
        try:
            os.unlink(p)
        except OSError:
            pass


def housekeeping(state, hours, dry):
    """Returns the number of state/ items removed or trimmed (never touches queue, runner, ledger, learned, domains, drafts in review)."""
    n, now = 0, time.time()
    day = 86400

    def old(p, secs):
        try:
            return now - os.lstat(p).st_mtime > secs
        except OSError:
            return False

    for name in ("events.jsonl.1",):
        p = os.path.join(state, "logs", name)
        if os.path.exists(p) and old(p, 7 * day):
            rm(p, dry)
            n += 1
    ev = os.path.join(state, "logs", "events.jsonl")
    if os.path.exists(ev) and not dry:
        keep, cut = [], now - 7 * day
        with open(ev, encoding="utf-8") as fh:
            lines = fh.readlines()
        for ln in lines:
            try:
                if json.loads(ln).get("ts", 0) >= cut:
                    keep.append(ln)
            except (ValueError, AttributeError, TypeError):
                pass
        if len(keep) != len(lines):
            n += len(lines) - len(keep)
            tmp = ev + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write("".join(keep))
            os.replace(tmp, ev)
    p = os.path.join(state, "queue.jsonl.bad")
    if os.path.exists(p) and old(p, 7 * day):
        rm(p, dry)
        n += 1
    for sub, secs in (("view", hours * 3600), ("backup", 7 * day), ("patches", 30 * day)):
        d = os.path.join(state, sub)
        if os.path.isdir(d):
            for name in sorted(os.listdir(d)):
                if old(os.path.join(d, name), secs):
                    rm(os.path.join(d, name), dry)
                    n += 1
    d = os.path.join(state, "draft")
    if os.path.isdir(d):
        for name in sorted(os.listdir(d)):
            try:
                with open(os.path.join(d, name, "meta.json"), encoding="utf-8") as fh:
                    status = json.load(fh).get("status")
            except (OSError, ValueError):
                continue
            if status == "failed" and old(os.path.join(d, name), 3 * day):
                rm(os.path.join(d, name), dry)
                n += 1
    return n


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--type", default="drama")
    ap.add_argument("--hours", type=float, default=24)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--quiet", action="store_true", help="print nothing when nothing was removed (cron)")
    ap.add_argument("--no-browser-temp", action="store_true")
    a = ap.parse_args(argv)
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,30}", a.type):
        print("ERROR --type must be a plain folder name such as drama or movie")
        return 2
    root = os.path.join(os.path.realpath(data_dir()), a.type)
    if not os.path.isdir(root):
        if not a.quiet:
            print(f"nothing to clean ({root} missing)")
        return 0
    state = os.path.join(root, "state")
    try:
        with open(os.path.join(state, "runner.json"), encoding="utf-8") as fh:
            runner = json.load(fh)
        live = time.time() - runner.get("ts", 0) < float(os.environ.get("DEVX_RUNNER_STALE", "2400"))
    except (OSError, ValueError, AttributeError):
        live = False
    if live and a.hours < 1 and not a.force:
        print("runner is active: skipped (use --force to override)")
        return 0
    cutoff, removed, kept = time.time() - a.hours * 3600, 0, 0
    targets = []
    for name in sorted(os.listdir(root)):
        p = os.path.join(root, name)
        if name == "state":
            continue
        if name == "work" and os.path.isdir(p) and not os.path.islink(p):
            targets += [os.path.join(p, t) for t in sorted(os.listdir(p))]
        else:
            targets.append(p)
    for p in targets:
        if os.path.islink(p):
            rm(p, a.dry_run)                                   # remove the link itself, never what it points to
            removed += 1
            continue
        if newest(p) < cutoff or a.hours <= 0:
            removed += 1
            rm(p, a.dry_run)
        else:
            kept += 1
    browser = 0
    if not a.no_browser_temp:
        tmpdir = tempfile.gettempdir()
        for pat in BROWSER_TEMP:
            for p in glob.glob(os.path.join(tmpdir, pat)):
                if not os.path.islink(p) and os.path.isdir(p) and newest(p) < cutoff:
                    browser += 1
                    rm(p, a.dry_run)
    pruned = 0
    ledger = os.path.join(state, "posted.jsonl")
    if os.path.exists(ledger) and not a.dry_run:
        keep, limit = [], time.time() - float(os.environ.get("DEVX_LEDGER_DAYS", "30")) * 86400
        with open(ledger, encoding="utf-8") as fh:
            for ln in fh:
                try:
                    if json.loads(ln).get("ts", 0) >= limit:
                        keep.append(ln)
                        continue
                except (ValueError, AttributeError, TypeError):
                    pass
                pruned += 1
        if pruned:
            tmp = ledger + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write("".join(keep))
            os.replace(tmp, ledger)
    house = housekeeping(state, a.hours, a.dry_run) if os.path.isdir(state) else 0
    if a.quiet and not (removed or browser or pruned or house):
        return 0
    print(f"{'would remove' if a.dry_run else 'removed'} {removed}, kept {kept} (older than {a.hours:g}h); browser temp {browser}; "
          f"state/ housekeeping {house}; queue/notes/domains untouched; ledger pruned {pruned}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
