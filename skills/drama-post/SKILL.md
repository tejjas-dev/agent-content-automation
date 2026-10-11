---
name: drama-post
description: >-
  Entry point of the drama pipeline. Post one or more dramas, given by name, to the user's Telegram
  channel(s) - find, scrape, shorten links, format, verify, send. Use whenever the user says things
  like "My Demon drama post kar", "ye 3 dramas daalo: A, B, C", "/drama-post <title>", or just lists
  drama names to publish.
---

# drama-post - runs the drama pipeline, one drama at a time

Env needed: `AROLINKS_TOKEN`, `TELEGRAM_BOT_TOKEN`, `DRAMA_POST_CHANNEL_IDS` (comma separated). Never print or ask for them.
DATA = `${DEVX_DATA_DIR:-$HOME/.devx-content}`. If a step fails for setup reasons run `python3 scripts/doctor.py` (once, not every run).

## Queue
Titles = what the user listed (keep season/year hints). Max 5; extras: reply "⏭️ <title>: limit (5) se aage, skip."
Do titles strictly one after another. After each, keep only its one-line result and drop page contents from your head.

## Per drama (load each skill when you reach its step; in Hermes they are `devx-content:<name>`)
1. `TASK=$DATA/work/<UTC-timestamp>-<title-slug>`; `mkdir -p "$TASK"`. All files of this drama live there.
2. **drama-find** -> chosen page URL + source. Ambiguous -> ask the user (up to 3 candidates), move on to the next title.
3. **drama-scrape** -> `data.json`, `links.json`.
4. **link-short** -> `short.json` (one script call for all links).
5. **drama-format** -> `caption1.txt`, `caption2.txt`, ...
6. **drama-verify** -> must say PASS (one fix attempt allowed, then give up on this drama).
7. **telegram-send** -> sends to every channel.
Do not delete the task folder: the `content-cleanup` skill does that later (cron).

## Replies (one short Hinglish line per drama; never paste captions, links or tokens)
- ok: `✅ Post bhej diya: <title> → <K> channel(s), <N> post(s).`
- partial: `⚠️ <title>: <ok>/<total> post gaye. Fail: <channel id> — <reason>.` (never resend the OK ones)
- not found: `Drama nahi mila.` | ambiguous: `Title ambiguous hai — exact drama confirm karo.` + candidates
- both sources failed: `Primary source par issue hai, backup bhi fail hua.` | Cloudflare: `Cloudflare challenge solve nahi hua.`
- no poster: `Poster available nahi hai.` | missing field: `Zaroori details extract nahi ho payi: <fields>.`
- no links: `Download links nahi mile, post send nahi kiya.` | shortening failed: `Links short nahi ho paye.`
- verify failed: `Post format nahi ban paya: <first problem>.` | send failed everywhere: `Channel me post send nahi ho paya: <channel> — <reason>.`

## Rules
- A post is never sent with a long (unshortened) link, without links, or after a failed verify.
- Model API 429 / rate limit: wait 60 s and continue; after 3 tries stop and tell the user.
- Learning: when you find a lasting structural fact about a source (URL pattern, selector, needs a challenge solver), append 1-2 lines to `$DATA/learned/<source>.md`. Skills read that file first.
- Never edit any SKILL.md silently. To improve a skill, show the user the exact diff and wait for OK. Script bugs: see the owning skill.
