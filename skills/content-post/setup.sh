#!/usr/bin/env sh
# Idempotent setup. Run inside the same environment the agent runs commands in
# (for a Docker terminal backend: inside the container).  Usage: setup.sh [--light]
#   --light : only bs4+lxml (plain http tier, ~20s). Default: also Scrapling + browsers (JS/Cloudflare sites).
exec python3 "$(dirname "$0")/scripts/content_post.py" setup "$@"
