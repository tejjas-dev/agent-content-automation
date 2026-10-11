#!/usr/bin/env python3
"""Delete old task folders. Meant for a cron job (no AI needed).  cleanup.py [--hours 24] [--dry-run]
Only touches <DATA>/work/* older than --hours. Keeps learned/ notes, the posted ledger and anything newer
(so a run in progress is never hit). DATA = $DEVX_DATA_DIR or ~/.devx-content."""
import argparse
import os
import shutil
import sys
import time


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=24)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    data = os.path.realpath(os.environ.get("DEVX_DATA_DIR") or os.path.join(os.path.expanduser("~"), ".devx-content"))
    work = os.path.join(data, "work")
    if not os.path.isdir(work):
        print(f"nothing to clean ({work} missing)")
        return 0
    cutoff, removed, kept = time.time() - a.hours * 3600, 0, 0
    for name in sorted(os.listdir(work)):
        p = os.path.join(work, name)
        if os.path.islink(p) or not os.path.isdir(p):
            continue                                            # never follow links out of work/
        newest = max([os.path.getmtime(p)] + [os.path.getmtime(os.path.join(r, f)) for r, _, fs in os.walk(p) for f in fs])
        if newest < cutoff:
            removed += 1
            if not a.dry_run:
                shutil.rmtree(p, ignore_errors=True)
        else:
            kept += 1
    print(f"{'would remove' if a.dry_run else 'removed'} {removed}, kept {kept} (older than {a.hours:g}h cleaned)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
