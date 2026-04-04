#!/bin/bash
# 🛸 MISSION: BYPASS & SANE (v38) - THE OLLAMA CURE
# Strategy: Injecting provider-level timeouts to prevent Ollama aborts.
set -e
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "=> 1. Generating Clean Config (v38)..."
bash generate-config.sh

echo "=> 2. REFRESHING INFRASTRUCTURE..."
# Clean state to ensure fresh config load
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

echo "=> 5. Re-launching Mission Control v38..."
pkill -f "python3.*mission_control.py" || true
# Clean up any stale logs
rm -f mission_logs_v38.out
nohup python3 -u mission_control.py > mission_logs_v38.out 2>&1 &

echo "=============================================================================="
echo "✅ MISSION: BYPASS & SANE COMPLETE (v38)"
echo "Strategy: Massive timeouts injected at Gateway, Provider and CLI levels."
echo "=============================================================================="
tail -f mission_logs_v38.out
