---
name: content-cleanup
description: >-
  Cleanup of a content pipeline's temporary data (drama now, movie/anime later) so the VPS stays clean: nothing
  scrape-related survives 24 hours. Meant for a scheduled cron job, or when the user says "cleanup kar",
  "purana data hata do". Never runs inside a post run.
---

# content-cleanup

```
python3 scripts/cleanup.py                    # drama: remove everything older than 24h, keep state/
python3 scripts/cleanup.py --dry-run          # only show what would go
python3 scripts/cleanup.py --quiet            # cron: prints nothing when nothing was removed
python3 scripts/cleanup.py --hours 0 --force  # wipe now (only when nothing is running)
python3 scripts/cleanup.py --type movie       # other content types (their own <DATA>/movie/ folder)
```
Reply with the single printed line.

| Removed after 24 h (`--hours`) | Always kept (never touched) |
|---|---|
| `work/<task>` folders: page.html, extract/data/links/short json, captions | `state/queue.jsonl`, `runner.json`, `domains.json` |
| stray files/folders in `<DATA>/<type>/` | `state/learned/*.md` (notes) |
| leftover browser temp folders of the scraper in the system temp dir (`playwright_*`, `.org.chromium.*`; `--no-browser-temp` to skip) | `state/posted.jsonl` (only lines older than `DEVX_LEDGER_DAYS`, default 30, are trimmed) |
| `state/view/*` (draft overlay copies, rebuilt on demand) | open drafts waiting for approval (`state/draft/`), except FAILED ones older than 3 days |

Also trimmed: `state/logs/events.jsonl` lines older than 7 days, `queue.jsonl.bad` > 7 days, `state/backup/*` > 7 days, `state/patches/*` > 30 days
(patches are meant to be committed to git: do it before they expire). DATA = `$DEVX_DATA_DIR`, else `/workspace`, else `~/.devx-content`.
The 24 h age limit means a run in progress is never touched; `--hours` below 1 with a live runner is refused unless `--force`.

## Schedule it (no AI, no tokens). Hourly keeps the worst case at ~25 h
- Any Linux VPS (`crontab -e`; use the absolute path of the installed skill and the same `DEVX_DATA_DIR` as the agent, if it is set):
  ```
  7 * * * * DEVX_DATA_DIR=/workspace python3 /path/to/skills/content-cleanup/scripts/cleanup.py --quiet
  ```
  Without `DEVX_DATA_DIR` the script finds the same folder the pipeline uses (`/workspace` if writable, else `~/.devx-content`). Daily instead of hourly: `0 4 * * *` (worst case ~48 h).
- Hermes: dashboard -> Cron, hourly job with the prompt "run the content-cleanup skill".
- Check it works: run once with `--dry-run`, then look at the line it prints.
