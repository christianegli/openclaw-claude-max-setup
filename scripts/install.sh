#!/usr/bin/env bash
# End-to-end installer for the billing-proxy-based OpenClaw stack on macOS.
# Idempotent: safe to rerun. Does not touch system paths outside ~/.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAUNCHD="$HOME/Library/LaunchAgents"
USER_NAME="$(id -un)"

need() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1"; exit 1; }; }

need node
need npm
need git
need python3

NODE_PATH="$(command -v node)"

# --- 1. secrets ----------------------------------------------------------------
if [[ -z "${OAUTH_TOKEN:-}" ]]; then
    cat >&2 <<'EOF'
OAUTH_TOKEN env var is required.

Get one with:
    claude setup-token
(copy the sk-ant-oat01-... printed to stdout)

Then:
    export OAUTH_TOKEN='sk-ant-oat01-...'
    ./scripts/install.sh
EOF
    exit 1
fi

# --- 2. clone the billing proxy -----------------------------------------------
if [[ ! -d "$HOME/openclaw-billing-proxy" ]]; then
    echo "==> cloning openclaw-billing-proxy"
    git clone https://github.com/zacdcook/openclaw-billing-proxy.git \
        "$HOME/openclaw-billing-proxy"
else
    echo "==> openclaw-billing-proxy already cloned"
fi

# --- 3. render launchd plists -------------------------------------------------
render() {
    local src="$1" dst="$2"
    sed -e "s|{{USER}}|$USER_NAME|g" \
        -e "s|{{NODE_PATH}}|$NODE_PATH|g" \
        -e "s|{{OAUTH_TOKEN}}|$OAUTH_TOKEN|g" \
        -e "s|{{REPO_PATH}}|$REPO|g" \
        "$src" > "$dst"
    chmod 600 "$dst"
}

echo "==> installing billing-proxy launchd agent"
render "$REPO/launchd-templates/com.example.billing-proxy.plist" \
       "$LAUNCHD/com.$USER_NAME.billing-proxy.plist"
launchctl unload "$LAUNCHD/com.$USER_NAME.billing-proxy.plist" 2>/dev/null || true
launchctl load -w "$LAUNCHD/com.$USER_NAME.billing-proxy.plist"

echo "==> installing stayawake launchd agent"
render "$REPO/launchd-templates/com.example.stayawake.plist" \
       "$LAUNCHD/com.$USER_NAME.stayawake.plist"
launchctl unload "$LAUNCHD/com.$USER_NAME.stayawake.plist" 2>/dev/null || true
launchctl load -w "$LAUNCHD/com.$USER_NAME.stayawake.plist"

# --- 4. wire openclaw config --------------------------------------------------
echo "==> wiring openclaw config"
python3 "$REPO/scripts/wire-openclaw.py"

# --- 5. restart openclaw gateway ---------------------------------------------
if command -v openclaw >/dev/null 2>&1; then
    echo "==> restarting openclaw gateway"
    openclaw gateway restart || echo "(gateway restart failed — restart manually later)"
fi

# --- 6. smoke test ------------------------------------------------------------
echo "==> waiting for billing proxy to become ready"
for i in 1 2 3 4 5 6 7 8 9 10; do
    if curl -sf "http://127.0.0.1:18801/health" >/dev/null; then
        echo "   ready"
        break
    fi
    sleep 1
done

curl -s "http://127.0.0.1:18801/health" || echo "(health endpoint not responding)"
echo
echo "==> done. Tail logs: tail -F /tmp/billing-proxy.log"
