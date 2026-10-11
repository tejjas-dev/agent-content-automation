#!/usr/bin/env python3
"""Daily cleanup of a content type's temporary data (cron friendly, no AI).
  cleanup.py [--type drama] [--hours 6] [--dry-run] [--force]

DATA = $DEVX_DATA_DIR, else /workspace if writable, else ~/.devx-content.   Target = DATA/<type>/
Removes everything in it except state/ (queue, posted ledger, learned notes, domains): work/<task> folders and any
stray file/folder older than --hours (default 6h, so a run in progress is never hit). Also trims posted.jsonl
lines older than 30 days. With --hours < 1 and a live runner it refuses unless --force."""
import argparse
import json
import os
import shutil
import sys
import time


def data_dir():
    e = os.environ.get("DEVX_DATA_DIR")
    if e:
        return e
    return "/workspace" if os.path.isdir("/workspace") and os.access("/workspace", os.W_OK) else os.path.join(os.path.expanduser("~"), ".devx-content")


def newest(p):
    return max([os.path.getmtime(p)] + [os.path.getmtime(os.path.join(r, f)) for r, _, fs in os.walk(p) for f in fs])


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--type", default="drama")
    ap.add_argument("--hours", type=float, default=6)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    root = os.path.join(os.path.realpath(data_dir()), a.type)
    if not os.path.isdir(root):
        print(f"nothing to clean ({root} missing)")
        return 0
    state = os.path.join(root, "state")
    try:
        runner = json.load(open(os.path.join(state, "runner.json")))
        live = time.time() - runner.get("ts", 0) < 2400
    except (OSError, ValueError):
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
            os.unlink(p) if not a.dry_run else None            # remove the link itself, never what it points to
            removed += 1
            continue
        if newest(p) < cutoff or a.hours <= 0:
            removed += 1
            if not a.dry_run:
                shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else os.unlink(p)
        else:
            kept += 1
    pruned = 0
    ledger = os.path.join(state, "posted.jsonl")
    if os.path.exists(ledger) and not a.dry_run:
        keep, limit = [], time.time() - 30 * 86400
        for ln in open(ledger, encoding="utf-8"):
            try:
                if json.loads(ln).get("ts", 0) >= limit:
                    keep.append(ln)
                    continue
            except ValueError:
                pass
            pruned += 1
        if pruned:
            open(ledger, "w", encoding="utf-8").write("".join(keep))
    print(f"{'would remove' if a.dry_run else 'removed'} {removed}, kept {kept} (older than {a.hours:g}h); state/ untouched; ledger pruned {pruned}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
