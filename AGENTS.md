# devx-content - instructions for any coding/automation agent

This repo is a set of **skills** (`skills/<name>/SKILL.md`) that run a content-posting pipeline. To post dramas, start at
`skills/drama-post/SKILL.md` and follow it; it loads the other skills step by step:

drama-post (entry, queue) -> drama-find -> drama-scrape -> link-short -> publish.py (drama-format + drama-verify + telegram-send)
and `content-cleanup` (cron, separate, no AI).

Rules for every agent:
- Do the AI work yourself (finding, matching, extracting gaps, handling errors). Scripts own what must be exact and cheap: `drama-post/scripts/drama.py`
  (paths, queue, task resume, domains, log), `publish.py`, `proposal.py`, `selftest.py`; `drama-find/scripts/pick.py` (Hindi-first ranking),
  `drama-scrape/scripts/fetch.py` + `extract.py`, `link-short/scripts/shorten.py`, `drama-format/scripts/build.py`, `drama-verify/scripts/check.py`,
  `telegram-send/scripts/send.py`, `content-cleanup/scripts/cleanup.py`. Scripts can fail: every failure prints a code, `drama-post/references/recovery.md` says what to do,
  and if no line fits you finish the step by hand and keep the pipeline moving.
- Secrets come from env (`AROLINKS_TOKEN`, `TELEGRAM_BOT_TOKEN`, `DRAMA_POST_CHANNEL_IDS`, optional `DEVX_NOTIFY_CHAT_ID`). Never print, log or commit them.
- All data of a pipeline lives in `<DATA>/<type>/` (DATA = `$DEVX_DATA_DIR`, else `/workspace`, else `~/.devx-content`): `work/` is temporary
  (cleaned after 24 h), `state/` is kept (queue, posted ledger, learned notes, domains, logs, drafts). Nothing of a pipeline is written outside that folder.
- **Never edit the installed skills in place while running the pipeline.** Lasting fixes (script bug, site structure, API change) go through a draft:
  `drama-post/scripts/proposal.py new/add/check`. A READY draft is used automatically by later runs (overlay), the main files stay untouched
  until the owner says approve (`proposal.py approve ID --user-approved`, which also writes a git patch). Never approve on your own.
- When maintaining this repo (not running the pipeline): keep stdlib only, keep each SKILL.md short (it is loaded into context on every use),
  run `python3 -m unittest discover -s tests`. `DATA` resolution is duplicated in `drama.py`, `send.py`, `cleanup.py`, `doctor.py`, `proposal.py`, `setup.sh` on purpose
  (skills stay self-contained): change all together. A drama the owner names is always posted (no cross-request dedupe; a database is planned for that).
