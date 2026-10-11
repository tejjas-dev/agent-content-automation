# devx-content - instructions for any coding/automation agent

This repo is a set of **skills** (`skills/<name>/SKILL.md`) that run a content-posting pipeline. To post dramas, start at
`skills/drama-post/SKILL.md` and follow it; it loads the other skills step by step:

drama-post (entry, queue) -> drama-find -> drama-scrape -> link-short -> publish.py (drama-format + drama-verify + telegram-send)
and `content-cleanup` (scheduled, separate).

Rules for every agent:
- Do the AI work yourself (finding, matching, scraping, extracting). Scripts own what must be exact: `drama-post/scripts/drama.py`
  (paths, queue, notify, domains), `drama-scrape/scripts/fetch.py`, `link-short/scripts/shorten.py`, `drama-format/scripts/build.py`,
  `drama-verify/scripts/check.py`, `telegram-send/scripts/send.py`, `content-cleanup/scripts/cleanup.py`.
- Secrets come from env (`AROLINKS_TOKEN`, `TELEGRAM_BOT_TOKEN`, `DRAMA_POST_CHANNEL_IDS`, optional `DEVX_NOTIFY_CHAT_ID`). Never print, log or commit them.
- All data of a pipeline lives in `<DATA>/<type>/` (DATA = `$DEVX_DATA_DIR`, else `/workspace`, else `~/.devx-content`): `work/` is temporary
  (cleaned daily), `state/` is kept (queue, posted ledger, learned notes, domains). Nothing of a pipeline is written outside that folder.
- If a script breaks, fix it minimally (stdlib only), tell the user, suggest committing. Change SKILL.md text only with the user's OK.
- Maintaining this repo: `python3 -m unittest discover -s tests`; keep each SKILL.md short (it is loaded into context on every use).
  `DATA` resolution is duplicated in `drama.py`, `send.py`, `cleanup.py`, `doctor.py`, `setup.sh` on purpose (skills stay self-contained): change all together.
