# agent-content-automation (`devx-content`)

Skills that let an AI agent post content to Telegram channels: **give names, the agent finds, scrapes, formats, verifies and sends**.
Drama now; movie and anime plug in later as more skills with their own sources and format.

| Skill | Job |
|---|---|
| `drama-post` | entry; one-by-one queue (max 5), replies |
| `drama-find` | search sources (katworld, fallback katdrama), spelling/language/same-name matching |
| `drama-scrape` | Scrapling extraction of title, audio, episodes, genre, poster, links |
| `link-short` | **script**: all links shortened in one call, labels stay paired with their link |
| `drama-format` | caption layout + balanced split (`measure.py` counts UTF-16) |
| `drama-verify` | **script**: layout, pairing, limits, only short links; then a human-style sanity look |
| `telegram-send` | **script**: poster URL then upload, retry_after, no duplicates |
| `content-cleanup` | **script** for cron: removes old task folders |

AI does the thinking; scripts only do what must be exact (shortening, counting, checking, sending, deleting). A link that fails to shorten loses its tag;
no links left means nothing is sent.

Install: see [INSTALL.md](INSTALL.md). Add movie/anime: copy the `drama-*` skills to `movie-*`, change sources and caption layout, add `MOVIE_POST_CHANNEL_IDS`
(`telegram-send --channels-env`, `link-short`, `content-cleanup` are shared as they are).
Tests: `python3 -m unittest discover -s tests`. Updates: bump `version` in `plugin.yaml` and `.claude-plugin/*.json`, push.
