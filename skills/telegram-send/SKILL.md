---
name: telegram-send
description: >-
  Send finished posts (poster image + caption) to every configured Telegram channel with a script that
  retries, honours rate limits and never duplicates. Use after drama-verify says PASS (also for
  movie/anime posts).
---

# telegram-send  (skill + script)

```
python3 scripts/send.py --task "$TASK"            # channels from $DRAMA_POST_CHANNEL_IDS
python3 scripts/send.py --task "$TASK" --channels-env MOVIE_POST_CHANNEL_IDS     # other content types
```
Reads `data.json` (title, poster) and `caption<N>.txt`. Sends every post, in order, to every channel: poster URL first, then image upload, `retry_after` respected. Prints `OK/SKIP/FAIL` per (channel, post) and `ok=N fail=M`.

- Already-delivered posts are skipped, so rerunning after a partial failure only sends what is missing. `--force` only if the user explicitly wants the drama posted again.
- Reasons: `chat not found` = wrong channel id; `not enough rights` / `bot is not a member` = make the bot admin with "post messages"; `Too Many Requests` = wait a minute and rerun.
- Never print the token. Only reply with the line defined in drama-post.

## If the script itself breaks (Telegram API changed)
Fix `scripts/send.py` minimally, rerun, tell the user what changed and suggest committing it. Keep stdlib-only.
