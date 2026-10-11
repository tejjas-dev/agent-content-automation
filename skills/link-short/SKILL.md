---
name: link-short
description: >-
  Shorten all download links of a post with AroLinks in a single script run, keeping every label
  paired with its own link. Use after drama-scrape (or movie/anime scrape) produced links.json.
---

# link-short  (skill + script)

```
python3 scripts/shorten.py "$TASK/links.json"      # writes $TASK/short.json
```
- One call shortens everything (4 parallel, one retry per failed link, same URL = one API call). Do not shorten links one by one yourself.
- `short.json` = `links.json` + `"short"` (an `https://arolinks.com/...` URL, or `null` if it failed). Order and label pairing are preserved by the script: never re-pair labels and URLs by hand.
- Never shorten the poster URL, never put a long link in a caption, never print `AROLINKS_TOKEN`.
- Output `shortened X/Y` with failed labels. Entries with `null` are dropped later by drama-format (their tag disappears from the post). If X = 0 -> `Links short nahi ho paye.` and stop.

## If the script itself breaks (API changed, new error)
You may fix `scripts/shorten.py` with the smallest possible change and rerun. Tell the user exactly what you changed and suggest committing it to the repo. Keep stdlib-only, keep the CLI and `short.json` format.
