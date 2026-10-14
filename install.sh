#!/usr/bin/env sh
# Copy (or --link) all skills into an agent's skills folder.  Re-run after `git pull` to update.
#   ./install.sh <hermes|claude|opencode|agents|openclaw|DIR> [--link]
# Hermes profile:  HERMES_HOME=~/.hermes/profiles/<name> ./install.sh hermes
# Safe update: each skill is copied beside the old one first and swapped in only after the copy succeeded.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
T="${1:-}"
[ -n "$T" ] || { sed -n '2,6p' "$0"; exit 1; }
case "$T" in
  hermes)   DEST="${HERMES_HOME:-$HOME/.hermes}/skills" ;;
  claude)   DEST="$HOME/.claude/skills" ;;
  opencode) DEST="$HOME/.config/opencode/skills" ;;
  agents)   DEST="$HOME/.agents/skills" ;;
  openclaw) DEST="$HOME/.openclaw/skills" ;;
  *)        DEST="$T" ;;
esac
mkdir -p "$DEST"
for d in "$HERE"/skills/*/; do
  n=$(basename "$d"); new="$DEST/.$n.new"; rm -rf "$new"
  if [ "${2:-}" = "--link" ]; then ln -s "${d%/}" "$new"; else cp -r "${d%/}" "$new"; fi
  rm -rf "$DEST/$n"; mv "$new" "$DEST/$n"
done
echo "Installed $(ls "$HERE/skills" | wc -l | tr -d ' ') skills into $DEST"
echo "Next: set AROLINKS_TOKEN, TELEGRAM_BOT_TOKEN, DRAMA_POST_CHANNEL_IDS for the agent, then run:"
echo "  sh $DEST/drama-post/scripts/setup.sh && python3 $DEST/drama-post/scripts/doctor.py --net"
echo "Cleanup (cron, hourly, no AI): see INSTALL.md 'Cleanup'."
