# agent-content-automation (`devx-content`)

Skills that let an AI agent post content to Telegram channels: **give names, the agent finds, scrapes, shortens, formats, verifies and sends**.
Drama now; movie and anime plug in later as more skills with their own sources and format.

| Skill | Job |
|---|---|
| `drama-post` | entry; request queue (several messages -> one drama at a time), crash resume (`task`/`step`), `publish.py` = build + verify + send, `proposal.py` = draft updates, `selftest.py`, `doctor.py` |
| `drama-find` | primary `new.katdrama.my`, fallback `katdrama.org`, moved domain found via `katworld.net/?type=KatDrama`; spelling/language/same-name matching, `pick.py` = Hindi-first ranking |
| `drama-scrape` | `fetch.py` (http / dynamic / stealth / auto tiers, backoff) + `extract.py` (compact page summary, so the AI reads ~10 lines) |
| `link-short` | **script**: all links shortened in one call, labels stay paired with their link, auth errors stop at once |
| `drama-format` | **script** `build.py`: locked caption layout + balanced split |
| `drama-verify` | **script** `check.py`: layout, pairing, limits, only short links |
| `telegram-send` | **script**: poster URL then upload, retry_after/backoff, resume without duplicates inside a task |
| `content-cleanup` | **script** for cron: nothing scrape-related survives 24 h, keeps `state/` |

AI does the thinking (find, match, fill gaps, handle errors); scripts do what must be exact and cheap. Scripts can fail: every failure prints a code
and [recovery.md](skills/drama-post/references/recovery.md) says what to do; if nothing fits the agent finishes the step by hand. A link that fails to shorten loses its tag; no links left = nothing is sent.
A drama you name is always posted (a database for duplicate handling is planned later).

```
<DATA>/drama/work/    per-drama task folders (temporary, cleaned after 24 h)
<DATA>/drama/state/   queue.jsonl, runner.json, posted.jsonl, domains.json, learned/<source>.md, logs/events.jsonl, draft/   (kept)
```

## Self-improving, with the owner in control
When a script breaks or a site changes, the agent finishes the current drama by hand, then (for lasting causes) makes a **draft**:
`proposal.py new / add / check`. The draft runs the offline `selftest.py`; only if it passes it becomes READY and later runs use it automatically (overlay),
so work continues while you are away. **Main skill files are not touched until you approve.** The agent adds one line to its reply
("🛠 Draft update ready ..."). You say `draft dikhao` (`proposal.py show ID`), then `approve <id>` (applies to the main skills, tests again, writes
`state/patches/<id>.patch` for git, cleans the draft) or `reject <id>`. Domain refresh (`drama.py domain refresh`) is the one automatic change: it only
follows the finder redirect to a verified live host and is reported in the reply.

Install: [INSTALL.md](INSTALL.md). Add movie/anime: copy the `drama-*` skills to `movie-*`, change sources and caption layout, add `MOVIE_POST_CHANNEL_IDS`
(`telegram-send --channels-env`, `link-short`, `content-cleanup --type movie` are shared).
Tests: `python3 -m unittest discover -s tests`. Release: bump `version` in `plugin.yaml` and `.claude-plugin/plugin.json`, `gemini-extension.json`, push.

## Configuration (all optional except the three tokens/ids)
| Env | Default | Meaning |
|---|---|---|
| `AROLINKS_TOKEN`, `TELEGRAM_BOT_TOKEN`, `DRAMA_POST_CHANNEL_IDS` | - | required |
| `DEVX_NOTIFY_CHAT_ID` | - | optional private Telegram alerts; without it alerts are written in the agent's reply |
| `DEVX_DATA_DIR` | `/workspace`, else `~/.devx-content` | where `drama/work` and `drama/state` live |
| `DEVX_RETRIES` | 2 | attempts per tier (fetch) / retry rounds (shorten) |
| `DEVX_BACKOFF`, `DEVX_BACKOFF_CAP` | 2, 30 (seconds) | exponential backoff base and cap; `0` = no waiting (tests) |
| `DEVX_RETRY_CAP` | 30 | max seconds to wait on Telegram `retry_after` |
| `DEVX_SEND_DELAY` | 3 | seconds between posts |
| `DEVX_RUNNER_STALE` | 2400 | seconds before a silent queue runner counts as dead |
| `DEVX_TASK_REUSE` | 21600 | an unfinished task of the same title younger than this is resumed |
| `DEVX_LEDGER_DAYS` | 30 | `posted.jsonl` lines older than this are trimmed by cleanup |
| `DEVX_SCRAPLING_VERSION` | 0.4.15 | version `setup.sh` installs (pinned, no silent upgrades) |
| `DEVX_SKILLS_DIR` | the folder of the scripts | only for tests / unusual layouts of `proposal.py` |

## Recovery (what to do when something is stuck)
- Queue stuck: `python3 drama.py status`, then `enqueue` with no titles (resume) or `reset --queue`. A damaged queue line is dropped automatically (`queue.jsonl.bad` keeps the original).
- Half-sent post: just request the same drama again within 6 h; the same task is resumed and only missing posts are sent. `timeout_uncertain` means Telegram may have posted it: check the channel first.
- Domain dead: `python3 drama.py domain refresh` (automatic via the agent); manual: `drama.py domain set primary https://...`.
- Check the whole setup: `python3 skills/drama-post/scripts/doctor.py --net`. Test a post without sending: `publish.py --task DIR --title "X" --dry-run`.
- What happened: `python3 drama.py status` (recent errors) or `<DATA>/drama/state/logs/events.jsonl` (secrets are redacted).
