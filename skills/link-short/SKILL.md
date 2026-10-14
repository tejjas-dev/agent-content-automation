---
name: link-short
description: >-
  Shorten all download links of a post with AroLinks in a single script run, keeping every label paired
  with its own link. Use after drama-scrape (or movie/anime scrape) produced links.json.
---

# link-short  (skill + script)

```
python3 $SK/link-short/scripts/shorten.py "$TASK/links.json"      # writes $TASK/short.json
```
- One call shortens everything (4 parallel, same URL = one API call, retries with exponential backoff, an auth error stops at once). Never shorten links one by one yourself.
- `short.json` = `links.json` + `"short"` (an `https://arolinks.com/...` URL, or `null` if it failed). Order and label pairing are preserved by the script: never re-pair labels and URLs by hand.
- Never shorten the poster URL, never put a long link in a caption, never print `AROLINKS_TOKEN`.
- Output `shortened X/Y` plus failed labels and `reasons:`. Entries with `null` lose their tag later (publish.py / drama-format). X = 0 -> `Links short nahi ho paye.` and stop.
- `CODE=AUTH` = token rejected: stop, tell the owner to check `AROLINKS_TOKEN` (retrying cannot help). `CODE=RATE|NETWORK`: wait 60 s, run once more. More in `drama-post/references/recovery.md`.

## If the script itself breaks (API changed, new error)
Do not edit `scripts/shorten.py` in place. Finish this run by hand if you can (one stdlib script inside `$TASK` calling the same API, token from env, never printed, same `short.json` format), then follow drama-post "Self-improve": a draft with the smallest fix, same CLI and `short.json` format, stdlib only.
