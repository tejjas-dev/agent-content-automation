---
name: drama-post
description: >-
  Entry point of the drama pipeline. Post one or more dramas, given by name, to the user's Telegram
  channel(s): find, scrape, shorten links, publish. Use whenever the user says things like "My Demon drama
  post kar", "ye 3 dramas daalo: A, B, C", "/drama-post <title>", or just lists drama names to publish.
---

# drama-post - runs the drama pipeline, one drama at a time

Env: `AROLINKS_TOKEN`, `TELEGRAM_BOT_TOKEN`, `DRAMA_POST_CHANNEL_IDS` (comma separated), optional `DEVX_NOTIFY_CHAT_ID`. Never print or ask for them.
Setup problems -> `python3 scripts/doctor.py` (not on every run). A drama the user names is always posted.

## 1. Start (every request)
```
python3 scripts/drama.py env        # prints SK, PY, DATA, ROOT (+ DRAFTS / NOTES only when draft updates are active)
python3 $SK/drama-post/scripts/drama.py enqueue "Title 1" "Title 2"     # ALL titles of the message, as written (keep season/year hints)
```
From here on run every script as `$SK/<skill>/scripts/...` (same files, draft-aware). If `NOTES=` was printed, read that short file once.
- `QUEUED position=N` -> a run is already working through the queue. Reply `⏳ Queue me hai (position N), pehle wala khatam hote hi ho jayega.` and STOP.
- `RUNNER` -> you process the queue (step 2). `SKIPPED_LIMIT <t>` (max 5 per message) / `DUPLICATE <t>` (already waiting in this queue) -> one line.
- Queue stuck: `enqueue` with no titles resumes it; `drama.py status`, `drama.py reset [--queue]` if asked.

## 2. Loop (RUNNER only; strictly one drama at a time)
Repeat `drama.py next` -> a title, or `EMPTY` (finished; stop). For each title:
1. `TASK=$(drama.py task "<title>")` then `drama.py step "$TASK"` -> `STEP FIND|SCRAPE|SHORT|PUBLISH`: start at that step (an unfinished task of the same title is reused after a crash; finished steps are never redone).
2. skill **drama-find** -> `$TASK/find.txt`. Ambiguous -> ask the user (up to 3 candidates), go to the next title.
3. skill **drama-scrape** -> `$TASK/data.json`, `$TASK/links.json`
4. skill **link-short** -> `$TASK/short.json`
5. `python3 $SK/drama-post/scripts/publish.py --task "$TASK" --title "<title>"` = build + verify + send. Relay its `REPLY` line. `--dry-run` = everything except sending.
   Problems listed: fix only those (skills drama-format, drama-verify), run publish.py once more.
Keep only the one-line result of each drama; drop page contents before the next.

## When something fails (AI handles it; scripts are helpers and can break)
1. Every script failure prints a `code=` / `CODE=`: look it up in `references/recovery.md` (one line each) and do exactly that.
2. Script broken or site changed and no recovery line fits: do that step by hand with AI inside `$TASK`, producing the same output files, and finish the drama. Log it: `drama.py log <stage> <code> "<short note>"`.
3. A lasting cause (site structure, domain, API change, script bug) -> make a **draft** (below). One-off hiccups are not drafts.
Token care: read the scripts' one-line output, never whole pages; use `extract.py` summaries; one fetch per page; `fetch.py` already retries and climbs tiers.

## Self-improve = drafts only (the owner approves, you never edit main files)
Never edit a SKILL.md, script or reference of the installed skills directly. Instead:
```
ID=$(python3 $SK/drama-post/scripts/proposal.py new "<short title>" --why "<cause + fix>" --note "<one instruction for later runs>")
python3 $SK/drama-post/scripts/proposal.py add $ID <skill>/<path>    # prints the draft file; edit THAT file (smallest change, stdlib only)
python3 $SK/drama-post/scripts/proposal.py check $ID                 # tests; READY = used automatically by later runs, main still untouched
```
- Check `proposal.py list` first (one draft per cause; max 5 open). `FAILED` -> fix the draft or `reject` it; `stale` (plugin updated since) -> `reject` and, if the problem remains, make a new one.
- While drafts exist add ONE line to your reply: `🛠 Draft update ready: <title> (<id>) - 'draft dikhao' / 'approve <id>' / 'reject <id>'`.
- Owner says show -> `proposal.py show ID`. Owner says approve -> `proposal.py approve ID --user-approved` (applies to main, writes a patch for git, cleans the draft). Reject -> `proposal.py reject ID`. Never approve on your own.
- Lasting facts about a source (1-2 lines) go to `$ROOT/state/learned/<source>.md` (read it first in drama-find/scrape); that file is notes, not code, no approval needed.

## Replies (one short Hinglish line per drama; never paste captions, links or tokens)
`publish.py` prints its own `REPLY ...`. For earlier failures: `Drama nahi mila.` | `Title ambiguous hai - exact drama confirm karo.` + candidates |
`Primary source par issue hai, backup bhi fail hua.` | `Cloudflare challenge solve nahi hua.` | `Poster available nahi hai.` |
`Zaroori details extract nahi ho payi: <fields>.` | `Download links nahi mile, post send nahi kiya.` | `Links short nahi ho paye.` |
domain changed (`DOMAIN_UPDATED`) -> `ℹ️ Primary domain badla: <old> -> <new> (auto update ho gaya).`

## Rules
- **Every file you create, including helper scripts, goes inside `$TASK`.** Never `/tmp`, never the workspace root, never outside `$ROOT`.
- Nothing is sent with a long link, without links, or after a failed verify. A retry of the SAME task only sends what is missing (`--force` = resend all, only if the user asks).
- Model API 429: wait 60 s and continue; after 3 tries stop and tell the user.
