#!/usr/bin/env sh
# Installs Scrapling (+ browsers) into $DEVX_DATA_DIR/venv. Idempotent. Run inside the agent's terminal/container.
set -e
D="${DEVX_DATA_DIR:-$HOME/.devx-content}"
mkdir -p "$D"
[ -x "$D/venv/bin/python" ] || python3 -m venv "$D/venv" || { echo "venv failed. Try: apt-get install -y python3-venv"; exit 1; }
"$D/venv/bin/pip" install -q -U "scrapling[fetchers]"
"$D/venv/bin/scrapling" install || echo "WARN: 'scrapling install' (browsers) failed; plain Fetcher still works. Re-run or check root/apt access."
echo "SETUP_OK  (use $D/venv/bin/python for Scrapling)"
