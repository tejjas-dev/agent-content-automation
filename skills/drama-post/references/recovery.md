# Recovery table: error code -> exactly what to do (read the one line, do not improvise)

| Where | Code / text | Do this |
|---|---|---|
| fetch.py | `BLOCKED` | `--tier stealth` (or `--tier auto`). Already stealth -> source failed, go to the next source. |
| fetch.py | `JS_SHELL` / `note=js_shell` | Page is only "Loading...": fetch again with `--tier dynamic` (primary search pages) and `--timeout 60`. |
| fetch.py | `NOT_FOUND` (404) | Wrong URL or dead domain. Primary: `drama.py domain refresh`, retry once. Page of a drama: next candidate. |
| fetch.py | `TIMEOUT` / `ERROR` / `HTTP_5xx` | Script already retried with backoff. Source failed -> next source. Never loop more. |
| fetch.py | `NOT_INSTALLED` | `sh $SK/drama-post/scripts/setup.sh`, use `$PY`. Until then only `--tier http` works. |
| fetch.py | `ATTEMPTS_EXHAUSTED` | Stop on this source (budget is 4). Next source, or `Primary source par issue hai, backup bhi fail hua.` |
| drama.py domain | `DOMAIN_UPDATED` | Retry the search once on the new domain; mention it in the reply. |
| drama.py domain | `DOMAIN_REFRESH_FAILED` | Use the fallback source. Never take a domain from page text. |
| extract.py | `EXTRACT PARTIAL missing=x` | Fill only x from the page (grep a few lines). title: pure name; poster: og:image/TMDB `<img>`; links: anchors to the download host. |
| extract.py | `EXTRACT FAIL js_shell` | Fetch again with `--tier dynamic`. |
| extract.py | `EXTRACT FAIL no_candidates` | Check the query spelling once (relaxed query), else `Drama nahi mila.` |
| shorten.py | `CODE=AUTH` | AroLinks token rejected. Stop: `Links short nahi ho paye.` + tell the owner to check `AROLINKS_TOKEN`. No retry. |
| shorten.py | `CODE=RATE` / `NETWORK` | Script retried with backoff. Wait 60 s, run shorten.py once more, else `Links short nahi ho paye.` |
| shorten.py | `failed: <labels>` but `shortened X/Y`, X>0 | Fine: those entries lose their tag. |
| publish.py | `Post format nahi ban paya: <problem>` | Fix only that problem (skills drama-format / drama-verify) and run publish.py once more. The task is marked `.failed`: the next request scrapes fresh. |
| send.py | `chat not found` | Wrong channel id in `DRAMA_POST_CHANNEL_IDS`. Tell the owner. |
| send.py | `not enough rights` / `bot is not a member` | Bot must be admin with "post messages". Tell the owner. |
| send.py | `Too Many Requests` | Wait a minute, rerun publish.py (only missing posts go out). |
| send.py | `timeout_uncertain` | Telegram may already have posted it. Tell the owner to check the channel; rerun only after they say so (`--force` only if they want it again). |
| proposal.py | `STALE` / status `stale` | The plugin was updated after the draft started. `proposal.py reject ID`; if the problem still exists make a new draft from the current files. |
| queue | `QUEUE_REPAIRED` | A damaged queue line was dropped (original in `queue.jsonl.bad`). Mention it once. |
| script itself | traceback / unknown output | Do the step by hand inside `$TASK` (same output files), finish the drama, then make a draft (drama-post, "Self-improve"). |
