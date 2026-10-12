#!/usr/bin/env sh
# Installs Scrapling (+ browsers) into a venv. Idempotent. Run inside the agent's terminal/container.
# Venv: $DEVX_DATA_DIR/venv, else /workspace/venv, else ~/.devx-content/venv; an existing old venv is reused.
# Scrapling is PINNED (no silent upgrades that could break scraping): default 0.4.15, override with DEVX_SCRAPLING_VERSION=x.y.z
set -e
if [ -n "$DEVX_DATA_DIR" ]; then D="$DEVX_DATA_DIR"
elif [ -d /workspace ] && [ -w /workspace ]; then D=/workspace
else D="$HOME/.devx-content"; fi
[ -x "$D/venv/bin/python" ] || [ ! -x "$HOME/.devx-content/venv/bin/python" ] || D="$HOME/.devx-content"
V="${DEVX_SCRAPLING_VERSION:-0.4.15}"
mkdir -p "$D"
[ -x "$D/venv/bin/python" ] || python3 -m venv "$D/venv" || { echo "venv failed. Try: apt-get install -y python3-venv"; exit 1; }
"$D/venv/bin/pip" install -q "scrapling[fetchers]==$V"
"$D/venv/bin/scrapling" install || echo "WARN: 'scrapling install' (browsers) failed; plain Fetcher still works but dynamic/stealth need it. Re-run or check root/apt access."
echo "SETUP_OK  (venv python: $D/venv/bin/python, scrapling $("$D/venv/bin/python" -c 'import importlib.metadata as m;print(m.version("scrapling"))' 2>/dev/null || echo '?'))"
