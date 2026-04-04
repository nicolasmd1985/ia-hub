#!/bin/bash
# 🛸 MISSION: BYPASS & SANE (v40) — THE FINAL CURE
# Strategy: 24h reasoning/embeddedPi timeout to prevent Ollama aborts.
set -e
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "=> 1. Generating Clean Config (v40)..."
bash generate-config.sh

echo "=> 2. REFRESHING INFRASTRUCTURE..."
# Ensure any previous zombie containers are gone
docker compose down
docker compose up -d

echo "=> 3. Stabilizing gateway..."
sleep 20

echo "=> 4. FINAL Health-Check..."
for i in {1..10}; do
  STATUS=$(docker inspect -f '{{.State.Health.Status}}' openclaw-gateway 2>/dev/null || echo "starting")
  echo "Status: $STATUS ($i/10)"
  if [ "$STATUS" == "healthy" ]; then break; fi
  sleep 5
done

echo "=> 5. Re-launching Mission Control v40..."
pkill -f "python3.*mission_control.py" || true
# Clean up any stale logs
rm -f mission_logs_v40.out
nohup python3 -u mission_control.py > mission_logs_v40.out 2>&1 &

echo "=============================================================================="
echo "✅ MISSION: BYPASS & SANE COMPLETE (v40)"
echo "Strategy: Embedded reasoning agent (embeddedPi) timeout set to 24h."
echo "=============================================================================="
tail -f mission_logs_v40.out
