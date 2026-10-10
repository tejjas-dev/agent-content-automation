# develx-agent-skills

Agent skills by DevelX. First one: **`content-post`**: give 1-5 drama names, it finds each on the
configured sites, builds the poster + caption post with shortened links, and sends it to your Telegram
channel(s). Movies/anime plug in later without touching the engine (`docs/ADDING_A_TYPE.md`).

**Design in one line:** a plain Python script does all mechanical work (no LLM tokens, no rate-limit pain);
the agent only passes titles in, relays the result, and repairs a site profile when a site changes layout.

## Install (Hermes)

```sh
# host, once per profile  (profile name is yours, e.g. scraper)
./install.sh <github-user>/<this-repo> scraper
# or by hand:
hermes -p scraper skills install <github-user>/<this-repo>/skills/content-post
```
Or just tell the agent: *"Install the skill from github.com/<github-user>/<this-repo> (skills/content-post), then run its setup and doctor."*

Secrets go in the profile's `.env` (never in the repo):
```
AROLINKS_TOKEN=...
TELEGRAM_BOT_TOKEN=...          # bot must be admin in every channel
DRAMA_POST_CHANNEL_IDS=-100123...,-100456...
```
Docker backend: if env vars don't reach the container, add them to `terminal.docker_forward_env` in the profile config.

## First run (inside the agent's terminal / container)
```sh
python3 skills/content-post/scripts/content_post.py setup     # once; --light = http tier only (fast)
python3 skills/content-post/scripts/content_post.py doctor    # env, deps, bot, channels
python3 skills/content-post/scripts/content_post.py run drama "My Unicorn Girl" --dry-run
```
`setup` is idempotent and self-heals: after a `docker rm` the first run reinstalls the light deps by itself.

## Use
Tell the bot: *"ye dramas post kar: A, B, C"*. Needs no flags. `force` = post again, `--dry-run` = test only.

## Update / maintain
`hermes -p scraper skills check` then `skills update`. Locally learned things (venv, AI-repaired profiles,
failure dumps, the posted ledger, logs) live in `~/.devx-content/` and survive updates.
A site changed? The script prints `[REPAIR ...]`, the agent fixes the profile via `references/repair.md`,
the fix is test-run before it is saved, and a later-failing fix auto-rolls back. Copy proven overrides
from `~/.devx-content/overrides/` into `skills/content-post/sources/` and push to make them permanent.

## Behaviour worth knowing
- Max 5 titles per request (rest skipped, reported). Sequential, one run at a time (lock).
- Same drama + same links is never posted twice to a channel (ledger); a partial failure resumes only the missing posts.
- Nothing is sent unless every final check passes; failures never reach the channels.
- Tokens are read from env only and redacted from logs and errors.

## Tests
`python3 -m unittest discover -s skills/content-post/scripts/tests -v` (offline: local fake site + Telegram/AroLinks mocks).
