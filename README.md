# agent-content-automation (`devx-content`)

Skills that let an AI agent post content to Telegram channels: **give names, the agent finds, scrapes, shortens, formats, verifies and sends**.
Drama now; movie and anime plug in later as more skills with their own sources and format.

| Skill | Job |
|---|---|
| `drama-post` | entry; request queue (several messages -> one drama at a time), `publish.py` = build + verify + send in one call |
| `drama-find` | search katworld, fallback katdrama (domains from `drama.py domain get`), spelling/language/same-name matching |
| `drama-scrape` | Scrapling extraction via `fetch.py` (http / dynamic / stealth tiers) |
| `link-short` | **script**: all links shortened in one call, labels stay paired with their link |
| `drama-format` | **script** `build.py`: locked caption layout + balanced split |
| `drama-verify` | **script** `check.py`: layout, pairing, limits, only short links |
| `telegram-send` | **script**: poster URL then upload, retry_after, no duplicates |
| `content-cleanup` | **script** for cron: wipes the temporary data daily, keeps `state/` |

AI does the thinking (find, match, scrape); scripts do what must be exact. A link that fails to shorten loses its tag; no links left = nothing is sent.

```
<DATA>/drama/work/    per-drama task folders (temporary, cleaned daily)
<DATA>/drama/state/   queue.jsonl, runner.json, posted.jsonl, domains.json, learned/<source>.md   (kept)
```
Domain moved? The agent verifies the new one, saves it with `drama.py domain set`, and (if `DEVX_NOTIFY_CHAT_ID` is set and you pressed /start on the bot) sends you a private message.

Install: [INSTALL.md](INSTALL.md). Add movie/anime: copy the `drama-*` skills to `movie-*`, change sources and caption layout, add `MOVIE_POST_CHANNEL_IDS`
(`telegram-send --channels-env`, `link-short`, `content-cleanup --type movie` are shared).
Tests: `python3 -m unittest discover -s tests`. Release: bump `version` in `plugin.yaml` and `.claude-plugin/plugin.json`, `gemini-extension.json`, push.
