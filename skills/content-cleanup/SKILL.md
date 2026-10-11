---
name: content-cleanup
description: >-
  Delete old temporary task folders of the content pipelines (drama/movie/anime). Meant for a
  scheduled cron job, or when the user says "cleanup kar", "purana data hata do". Never runs inside a
  post run.
---

# content-cleanup

```
python3 scripts/cleanup.py --hours 24            # remove task folders older than 24h
python3 scripts/cleanup.py --dry-run             # only show what would go
```
Only touches `$DATA/work/*` older than `--hours` (DATA = `${DEVX_DATA_DIR:-$HOME/.devx-content}`). Newer folders (a run in progress) are never touched; `learned/` notes and `posted.jsonl` are kept. Reply with the single printed line.

## Schedule it (no AI needed, no tokens)
- Any system: `0 4 * * * python3 /path/to/skills/content-cleanup/scripts/cleanup.py --hours 24`
- Hermes: dashboard -> Cron, daily job with the prompt "run the content-cleanup skill".
