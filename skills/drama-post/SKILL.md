---
name: drama-post
description: >-
  Entry point of the drama pipeline. Post one or more dramas, given by name, to the user's Telegram
  channel(s): find, scrape, shorten links, publish. Use whenever the user says things like "My Demon drama
  post kar", "ye 3 dramas daalo: A, B, C", "/drama-post <title>", or just lists drama names to publish.
---

# drama-post - runs the drama pipeline, one drama at a time

Env: `AROLINKS_TOKEN`, `TELEGRAM_BOT_TOKEN`, `DRAMA_POST_CHANNEL_IDS` (comma separated), optional `DEVX_NOTIFY_CHAT_ID`. Never print or ask for them.
`scripts/` below is relative to THIS skill's folder. Setup problems -> `python3 scripts/doctor.py` (not on every run).

## 1. Start (every request)
```
python3 scripts/drama.py env                      # prints SK, PY, DATA, ROOT - use these, never guess paths
python3 scripts/drama.py enqueue "Title 1" "Title 2"     # ALL titles of the user's message, as written (keep season/year hints)
```
- `QUEUED position=N` -> a run is already working through the queue. Reply `⏳ Queue me hai (position N), pehle wala khatam hote hi ho jayega.` and STOP.
- `RUNNER` -> you process the queue (step 2). `SKIPPED_LIMIT <t>` (max 5 per message) / `DUPLICATE <t>` -> mention in one line.
- User says the queue is stuck: `enqueue` with no titles resumes it; `drama.py status`, `drama.py reset [--queue]` if asked.

## 2. Loop (RUNNER only; strictly one drama at a time, then ask for the next)
Repeat `python3 scripts/drama.py next` -> a title, or `EMPTY` (finished; stop). For each title:
1. `TASK=$(python3 scripts/drama.py task "<title>")`
2. skill **drama-find** -> `$TASK/find.txt`. Ambiguous -> ask the user (up to 3 candidates), go to the next title.
3. skill **drama-scrape** -> `$TASK/data.json`, `$TASK/links.json`
4. skill **link-short** -> `$TASK/short.json`
5. `python3 scripts/publish.py --task "$TASK" --title "<title>"` = build captions + verify + send in one call. Relay its `REPLY` line.
   `PUBLISH_FAIL`/problems listed: fix only those (skills drama-format, drama-verify), run publish.py once more.
Keep only the one-line result of each drama; drop page contents before the next.

## Replies (one short Hinglish line per drama; never paste captions, links or tokens)
`publish.py` prints its own `REPLY ...`. For earlier failures: `Drama nahi mila.` | `Title ambiguous hai - exact drama confirm karo.` + candidates |
`Primary source par issue hai, backup bhi fail hua.` | `Cloudflare challenge solve nahi hua.` | `Poster available nahi hai.` |
`Zaroori details extract nahi ho payi: <fields>.` | `Download links nahi mile, post send nahi kiya.` | `Links short nahi ho paye.`

## Rules
- **Every file you create, including helper scripts, goes inside `$TASK`.** Never `/tmp`, never the workspace root, never outside `$ROOT`.
- Nothing is sent with a long link, without links, or after a failed verify. Dedupe is automatic (`--force` only if the user asks to post again).
- Model API 429: wait 60 s and continue; after 3 tries stop and tell the user.
- Learning: lasting structural facts about a source -> 1-2 lines in `$ROOT/state/learned/<source>.md` (read it first in drama-find/scrape). Never edit a SKILL.md silently; show the diff and wait for OK.
