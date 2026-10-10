#!/usr/bin/env sh
# Host-side installer for Hermes.  Usage: ./install.sh <github-user>/<repo> [profile]
# Installs the skill into the profile. The in-container setup is done by the agent (or by you) afterwards.
set -e
REPO="${1:?usage: ./install.sh <github-user>/<repo> [profile]}"
H="hermes"; [ -n "$2" ] && H="hermes -p $2"
$H skills install "$REPO/skills/content-post" || { $H skills tap add "$REPO" && $H skills install content-post; }
echo
echo "Next: put AROLINKS_TOKEN, TELEGRAM_BOT_TOKEN, DRAMA_POST_CHANNEL_IDS in the profile's .env"
echo "      (~/.hermes/profiles/<profile>/.env), restart the gateway, then tell the agent:"
echo "      'content-post skill: run setup, then doctor, then a dry-run of one drama'"
