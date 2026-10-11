---
name: telegram-send
description: >-
  Send finished posts (poster image + caption) to every configured Telegram channel with a script that
  retries, honours rate limits and never duplicates. Normally run by publish.py; also usable for
  movie/anime posts.
---

# telegram-send  (skill + script)

```
python3 $SK/telegram-send/scripts/send.py --task "$TASK"                                   # channels: $DRAMA_POST_CHANNEL_IDS
python3 $SK/telegram-send/scripts/send.py --task "$TASK" --channels-env MOVIE_POST_CHANNEL_IDS   # other content types
```
Reads `data.json` (title, poster) and `caption<N>.txt`. Sends every post, in order, to every channel: poster URL first, then image upload, `retry_after` respected. Prints `OK/SKIP/FAIL` per (channel, post) and `ok=N fail=M`.

- Delivered posts are recorded in `$ROOT/state/posted.jsonl` and skipped on rerun, so a retry only sends what is missing. `--force` only if the user explicitly wants it posted again.
- Reasons: `chat not found` = wrong channel id; `not enough rights` / `bot is not a member` = make the bot admin with "post messages"; `Too Many Requests` = wait a minute and rerun.
- Never print the token. If the script itself breaks (Telegram API changed): fix `scripts/send.py` minimally (stdlib only), rerun, tell the user, suggest committing.
