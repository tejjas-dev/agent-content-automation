# Install

Skills are plain folders, so any agent works. Pick yours; **verified** = confirmed in the agent's docs, **unverified** = standard path, not tested here.

| Agent | Command |
|---|---|
| **Hermes** (verified) | `hermes plugins install tejjas-dev/agent-content-automation --enable` (asks for the 3 env values, saves them to the profile `.env`). Other profile: `hermes -p <profile> plugins install ...`. Update: `hermes plugins update devx-content` |
| **Claude Code** (manifests included) | `/plugin marketplace add tejjas-dev/agent-content-automation` then `/plugin install devx-content@devx` |
| **OpenCode** (unverified path) | `git clone` this repo, `./install.sh opencode` |
| **Codex / Antigravity / other `.agents/skills` readers** (unverified path) | `./install.sh agents` (or `./install.sh DIR` for any skills folder) |
| **OpenClaw** (unverified path) | `./install.sh openclaw` |
| **Gemini CLI** (unverified) | `gemini extensions install https://github.com/tejjas-dev/agent-content-automation` (reads `AGENTS.md`) |
| **Anything else** | Tell the agent: "Install the skills in `skills/` of this repo as skills, then follow `skills/drama-post/SKILL.md`." |

Update for the `install.sh` route: `git pull && ./install.sh <agent>`. Use `--link` to symlink so `git pull` alone updates.

## First run (inside the environment where the agent runs commands, e.g. the Docker container or the VPS)
```sh
sh skills/drama-post/scripts/setup.sh                 # Scrapling 0.4.15 (pinned) + browsers, once (idempotent; an old venv, e.g. ~/.devx-content/venv, is reused)
python3 skills/drama-post/scripts/doctor.py --net     # env, deps, bot, channels, AroLinks token (1 test link), primary/fallback/finder sites
```
Optional env: `DEVX_NOTIFY_CHAT_ID` = your Telegram user id (press /start on the bot once) for private alerts. Without it, alerts (domain changed, draft update ready)
appear in the agent's reply. Full option list: [README.md](README.md#configuration-all-optional-except-the-three-tokensids).
Then tell the agent: "my demon drama post kar". Several messages at once are queued and processed one by one.
Safe test of the whole chain without posting: ask the agent for a dry run (`publish.py ... --dry-run` builds and verifies, sends nothing).

## Sources and domains
Primary `https://new.katdrama.my/` (search `?q=`, results by JavaScript), fallback `https://katdrama.org/` (Cloudflare, stealth tier), finder
`https://katworld.net/?type=KatDrama` (redirects to the live primary domain). Saved overrides live in `<DATA>/drama/state/domains.json`
(`python3 skills/drama-post/scripts/drama.py domain get|set|refresh`). Old names `katdrama` / `katworld` still work as aliases of `primary` / `finder`.

## Draft updates (self-improvement with your approval)
```sh
python3 skills/drama-post/scripts/proposal.py list              # drafts: id, status (ready = active for later runs), title
python3 skills/drama-post/scripts/proposal.py show <id>         # why, tests, diff
python3 skills/drama-post/scripts/proposal.py approve <id> --user-approved   # apply to the installed skills, tests again, write patch
python3 skills/drama-post/scripts/proposal.py reject <id>       # drop the draft
```
Normally you just tell the agent "approve <id>" / "reject <id>". An approved change is written to the INSTALLED skills and a patch is saved in
`<DATA>/drama/state/patches/<id>.patch` (kept 30 days): apply it to your clone (`git apply <id>.patch`), commit and push, otherwise `hermes plugins update` /
`./install.sh` will overwrite the change with the repo version. Drafts, their copies and logs are cleaned by the cleanup job (see below).
A draft whose main file was updated after the draft started (for example by a plugin update) turns `stale`: it stops being used and cannot be approved,
so it can never silently undo the newer repo version. `reject` it; the agent makes a new draft from the current files if the problem still exists.

## Upgrading from 0.3.x
`hermes plugins update devx-content` (or `git pull && ./install.sh <agent>`), then `sh skills/drama-post/scripts/setup.sh` once (pins Scrapling) and `doctor.py --net`.
The first `drama.py env` copies old `learned/*.md` and `posted.jsonl` into `<DATA>/drama/state/` automatically. Changes to know: `katworld` is no longer a search source
(primary is `new.katdrama.my`), a drama you ask for is always posted again (the ledger only prevents re-sending inside the same task), cleanup keeps files 24 h instead of 6 h.

## Cleanup (cron, no AI, keeps the VPS clean: nothing scrape-related survives 24 h)
Hourly (worst case ~25 h; use the same `DEVX_DATA_DIR` as the agent if you set one):
```
7 * * * * DEVX_DATA_DIR=/workspace python3 /path/to/skills/content-cleanup/scripts/cleanup.py --quiet
```
Or daily `0 4 * * *` (worst case ~48 h), or Hermes dashboard -> Cron with the prompt "run the content-cleanup skill". Check first with `--dry-run`.
It removes `work/` tasks, stray files, scraper browser temp folders, old logs/backups/overlay copies; it never touches the queue, domains, notes, ledger (30-day trim) or drafts waiting for you.
Details: `skills/content-cleanup/SKILL.md`.
