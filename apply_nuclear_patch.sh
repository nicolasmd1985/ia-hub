#!/bin/bash
# 🛸 MISSION: BYPASS & SANE (v42) — THE IDLE TIMEOUT CURE
# Strategy: llm.idleTimeoutSeconds set to 24h to fix slow Ollama starts.
set -e
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "=> 1. Generating Clean Config (v42)..."
bash generate-config.sh

echo "=> 2. REFRESHING INFRASTRUCTURE..."
# Ensure fresh config reload and env variable injection
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

echo "=> 5. Re-launching Mission Control v42..."
pkill -f "python3.*mission_control.py" || true
# Clean up any stale logs
rm -f mission_logs_v42.out
nohup python3 -u mission_control.py > mission_logs_v42.out 2>&1 &

echo "=============================================================================="
echo "✅ MISSION: BYPASS & SANE COMPLETE (v42)"
echo "Strategy: llm.idleTimeoutSeconds fixed. Model Keep-Alive enforced."
echo "=============================================================================="
tail -f mission_logs_v42.out
