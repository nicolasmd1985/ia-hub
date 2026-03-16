#!/bin/bash

# ─────────────────────────────────────────────────────────────────────────────
#  OpenClaw Config Generator
#  Generates openclaw.json from openclaw.json.template using .env variables
# ─────────────────────────────────────────────────────────────────────────────

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"
TEMPLATE_FILE="$SCRIPT_DIR/openclaw-docker/openclaw.json.template"
OUTPUT_FILE="$SCRIPT_DIR/openclaw-docker/openclaw.json"

# Load .env
if [ -f "$ENV_FILE" ]; then
    export $(grep -v '^#' "$ENV_FILE" | xargs)
fi

# Determine Host IP (Tailscale preferred if available, otherwise first local IP)
HOST_IP=$(hostname -I | awk '{print $1}')
if command -v tailscale >/dev/null 2>&1; then
    TS_IP=$(tailscale ip -4 | head -n 1)
    if [ ! -z "$TS_IP" ]; then
        HOST_IP=$TS_IP
    fi
fi

# Override with ENV if provided
HOST_IP=${OPENCLAW_HOST_IP:-$HOST_IP}
ALLOWED_ORIGIN="http://$HOST_IP:18789"

echo "⚙️ Generating OpenClaw config..."
echo "📍 Host IP: $HOST_IP"

# Base configuration from template
CONFIG=$(cat "$TEMPLATE_FILE")

# 1. Update Allowed Origins & Pairing Settings
# We allow localhost and the detected IP
# We also enable dangerouslyDisableDeviceAuth to avoid the "pairing required" screen for local/VPN usage
CONFIG=$(echo "$CONFIG" | jq --arg origin "$ALLOWED_ORIGIN" \
    '.gateway.controlUi.allowedOrigins = ["http://localhost:18789", $origin] |
     .gateway.controlUi.dangerouslyDisableDeviceAuth = true |
     .gateway.controlUi.allowInsecureAuth = true')

# 2. Filter Agents
# If OPENCLAW_AGENTS is provided (comma-separated list of IDs)
if [ ! -z "$OPENCLAW_AGENTS" ]; then
    echo "🤖 Filtering agents: $OPENCLAW_AGENTS"
    # Convert comma-separated to space-separated for JQ
    AGENT_LIST=$(echo "$OPENCLAW_AGENTS" | tr ',' ' ' )
    
    # Filter agents.list by id
    # We use index based filtering or select
    CONFIG=$(echo "$CONFIG" | jq --arg agents "$OPENCLAW_AGENTS" '
        .agents.list as $full_list |
        ($agents | split(",")) as $wanted |
        .agents.list = ($full_list | map(select(.id as $id | $wanted | contains([$id]))))
    ')
else
    echo "🤖 Using all preset agents."
fi

# Write output
echo "$CONFIG" > "$OUTPUT_FILE"
echo "✅ Configuration generated at $OUTPUT_FILE"
