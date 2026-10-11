---
name: content-cleanup
description: >-
  Daily cleanup of a content pipeline's temporary data (drama now, movie/anime later) so the VPS stays
  clean. Meant for a scheduled cron job, or when the user says "cleanup kar", "purana data hata do".
  Never runs inside a post run.
---

# content-cleanup

```
python3 scripts/cleanup.py                 # drama: remove everything older than 6h, keep state/
python3 scripts/cleanup.py --dry-run       # only show what would go
python3 scripts/cleanup.py --hours 0 --force   # wipe now (only when nothing is running)
python3 scripts/cleanup.py --type movie    # other content types (their own <DATA>/movie/ folder)
```
All data of a pipeline lives in `<DATA>/<type>/` (DATA = `$DEVX_DATA_DIR`, else `/workspace`, else `~/.devx-content`):
`work/` (task folders and anything temporary) is cleaned; `state/` (queue, posted ledger, learned notes, domains) is always kept
(the ledger only loses lines older than 30 days). The default 6 h age limit means a run in progress is never touched.
Reply with the single printed line.

## Schedule it daily (no AI needed, no tokens)
- Any system: `0 4 * * * python3 /path/to/skills/content-cleanup/scripts/cleanup.py`
- Hermes: dashboard -> Cron, daily job with the prompt "run the content-cleanup skill".
