---
name: content-post
description: Scrape named dramas (movies/anime later) and post each as a poster+caption to the user's Telegram channel(s) with shortened download links. Use this whenever the user asks to post, scrape, find, or publish one or more dramas by name, e.g. "My Unicorn Girl post kar", "ye 3 dramas daalo: A, B, C", "/drama-post <title>", even when they only list titles.
version: 0.1.0
required_environment_variables:
  - name: AROLINKS_TOKEN
    prompt: AroLinks API token
    help: AroLinks dashboard -> API token
    required_for: shortening download links
  - name: TELEGRAM_BOT_TOKEN
    prompt: Telegram bot token
    help: BotFather -> your bot -> API token (bot must be admin in every channel)
    required_for: sending posts to the channel(s)
  - name: DRAMA_POST_CHANNEL_IDS
    prompt: Drama channel id(s), comma separated
    help: e.g. -1001234567890,-1009876543210
    required_for: choosing which channel(s) get drama posts
---

# content-post

A script does all the work (search, scrape, shorten, caption, checks, send, dedupe, cleanup).
Your job: pass the titles in, relay the result. Do not scrape, curl, shorten or send anything yourself.

## Run (one command; use a terminal timeout of at least 600s)

```
python3 ${HERMES_SKILL_DIR}/scripts/content_post.py run drama "Title 1" "Title 2" "Title 3"
```
(Other agents: the script is `scripts/content_post.py` next to this file.)

- Pass titles exactly as the user wrote them (keep season/year hints like "Season 2" or "2024"). One quoted argument per title.
- Add `--force` only if the user explicitly wants a drama posted again. Add `--dry-run` if they want a test without sending.
- More than 5 titles: the script skips the extras itself and says so.

## Read the output

Every printed line is already user-facing Hinglish. Reply with those lines as they are. Never paste captions, links or tokens.

- `[REPAIR source=... dump=...]` on a line: the site layout changed. Read `references/repair.md` and follow it once for that title.
- `❓ ... ambiguous`: show the candidates to the user and ask which one; then rerun with the exact title.
- `SETUP_NEEDED` or `⚙️ Setup adhura hai`: run `python3 ${HERMES_SKILL_DIR}/scripts/content_post.py setup` once (can take minutes), then rerun. Missing env vars must be set by the user in the profile's `.env`.
- `⏭️ ... time budget`: tell the user to send those titles again.
- Anything else: relay and stop. Do not retry on your own.

Health check when something feels off: `python3 ${HERMES_SKILL_DIR}/scripts/content_post.py doctor`.
