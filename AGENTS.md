# devx-content - instructions for any coding/automation agent

This repo is a set of **skills** (`skills/<name>/SKILL.md`) that run a content-posting pipeline. To post dramas, start at
`skills/drama-post/SKILL.md` and follow it; it loads the other skills step by step:

drama-post (entry, queue) -> drama-find -> drama-scrape -> link-short -> drama-format -> drama-verify -> telegram-send
and `content-cleanup` (scheduled, separate).

Rules for every agent:
- Do the AI work yourself (finding, matching, scraping, formatting). Use the bundled scripts only for what they own:
  `link-short/scripts/shorten.py`, `drama-verify/scripts/check.py`, `telegram-send/scripts/send.py`,
  `drama-format/scripts/measure.py`, `content-cleanup/scripts/cleanup.py`.
- Secrets come from env (`AROLINKS_TOKEN`, `TELEGRAM_BOT_TOKEN`, `DRAMA_POST_CHANNEL_IDS`). Never print, log or commit them.
- Task data lives in `${DEVX_DATA_DIR:-$HOME/.devx-content}` (outside the skills). Learned notes: `learned/<source>.md`.
- If a script breaks, fix it minimally (stdlib only), tell the user, suggest committing. Change SKILL.md text only with the user's OK.
- Maintaining this repo: run `python3 -m unittest discover -s tests`; keep each SKILL.md short (it is loaded into context on every use).
