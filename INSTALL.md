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

## First run (inside the environment where the agent runs commands, e.g. the Docker container)
```sh
sh skills/drama-post/scripts/setup.sh                 # Scrapling + browsers, once (idempotent; an old venv is reused)
python3 skills/drama-post/scripts/doctor.py --net     # env, deps, bot, channels
```
Optional env: `DEVX_NOTIFY_CHAT_ID` = your Telegram user id (press /start on the bot once) for private alerts such as "domain changed".
Then tell the agent: "my demon drama post kar". Several messages at once are queued and processed one by one.

## Upgrading from 0.2.x
`hermes plugins update devx-content` (or `git pull && ./install.sh <agent>`). The first `drama.py env` copies your old
`learned/*.md` and `posted.jsonl` into `<DATA>/drama/state/` automatically.

## Daily cleanup (cron, no AI)
`0 4 * * * python3 <skills>/content-cleanup/scripts/cleanup.py` - or Hermes dashboard -> Cron with the prompt "run the content-cleanup skill".
Removes everything under `<DATA>/drama/` older than 6 h except `state/`.
