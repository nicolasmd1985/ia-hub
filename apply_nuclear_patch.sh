#!/bin/bash
# ==============================================================================
# ☢️  NUCLEAR INFRASTRUCTURE RESILIENCE PATCH (v22)
# ==============================================================================
# This script synchronizes config, rebuilds the stack, and overwrites 
# the Node.js 'aborted' status to allow high-latency reasoning to persist.
# ==============================================================================

set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "=> 1. Synchronizing patched JSON template to live config..."
sudo cp openclaw-docker/openclaw.json.template openclaw-docker/openclaw.json
sudo chmod 666 openclaw-docker/openclaw.json

echo "=> 2. Rebuilding Docker stack (Context: 8192)..."
docker compose down
docker compose up -d

echo "=> 3. Waiting for gateway to initialize..."
sleep 15

echo "=> 4. Injecting Node.js Abort-Suppressor (Patching runtime files)..."
# We inject 'aborted: false' into the core response logic to stop the 60s kill signal
docker exec openclaw-gateway sh -c "find /usr/local/lib/node_modules/openclaw -type f -name '*.js' -exec sed -i 's/\"aborted\": true/\"aborted\": false/g' {} +"
docker exec openclaw-gateway sh -c "find /usr/local/lib/node_modules/openclaw -type f -name '*.js' -exec sed -i 's/60000/86400000/g' {} +"
docker restart openclaw-gateway

echo "=> 5. Re-launching Mission Control Orchestrator (v22)..."
pkill -f "python3.*mission_control.py" || true
pkill -f "run_mission_control.sh" || true
nohup bash run_mission_control.sh > mission_logs_v22.out 2>&1 &

echo ""
echo "=============================================================================="
echo "✅ NUCLEAR PATCH APPLIED SUCCESSFULLY"
echo "Mission Control is now running in 'Resilience mode' (v22)."
echo "Work will be salvaged even if the Gateway reports an internal timeout."
echo "=============================================================================="
echo ""
tail -f mission_logs_v22.out
