#!/bin/bash

# ─────────────────────────────────────────────────────────────────────────────
#  Mission Control Loop Driver
#  Runs the orchestrator every 5 minutes to poll for new tasks.
# ─────────────────────────────────────────────────────────────────────────────

# Absolute path to absolute directory
DIR="/home/nicolasmd/Development/agents-developmet/ai-hub"
INTERVAL=300  # 5 minutes in seconds

echo "====================================================="
echo " 🛸 Mission Control Autonomous Loop Activated"
echo " Polling GitHub Project board every $INTERVAL seconds..."
echo "====================================================="

while true; do
    echo "[$(date)] 🛰️ Checking board..."
    # Run absolute with Unbuffered output flag
    python3 -u "$DIR/mission_control.py"
    
    echo "[$(date)] 💤 Sleeping for $INTERVAL seconds..."
    sleep $INTERVAL
done
