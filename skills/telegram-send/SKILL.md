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
Reads `data.json` (title, poster) and `caption<N>.txt`. Sends every post, in order, to every channel: poster URL first, then image upload, `retry_after` respected, else exponential backoff. Prints `OK/SKIP/FAIL` per (channel, post) and `ok=N fail=M`.

- Delivered posts are recorded per task in `$ROOT/state/posted.jsonl`: rerunning the SAME task only sends what is missing. A new request for the same drama is a new task and is always sent. `--force` resends everything (only if the user asks).
- A read timeout is never retried (Telegram may have posted it): `timeout_uncertain` -> tell the owner to check the channel first.
- Reasons: `chat not found` = wrong channel id; `not enough rights` / `bot is not a member` = make the bot admin with "post messages"; `Too Many Requests` = wait a minute and rerun.
- Never print the token. If the script itself breaks (Telegram API changed): do not edit it in place; send by hand with a small stdlib script inside `$TASK` (token from env, never printed, same ledger line format), then follow drama-post "Self-improve" (draft).
