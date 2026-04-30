#!/bin/bash
# 🛸 MISSION: MULTI-MODEL PIPELINE (v43)
# Strategy: Dedicated models per agent role + persistent state + instance locking.
# Models: qwen2.5-coder:3b (Backend/Frontend), llama3.2:3b (QA), qwen2.5:1.5b (Architect/Analyst)
set -e
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# ── Safety: Ensure OPENCLAW_AGENTS includes qa if set ────────────────────────
if grep -q "^OPENCLAW_AGENTS=" .env 2>/dev/null; then
  AGENTS_VAR=$(grep "^OPENCLAW_AGENTS=" .env | cut -d= -f2)
  if [ -n "$AGENTS_VAR" ] && ! echo "$AGENTS_VAR" | grep -q "qa"; then
    echo "⚠️  WARNING: OPENCLAW_AGENTS in .env does not include 'qa'."
    echo "   The QA agent is REQUIRED for the TDD pipeline."
    echo "   Adding qa,architect,analyst to OPENCLAW_AGENTS..."
    sed -i "s/^OPENCLAW_AGENTS=.*/OPENCLAW_AGENTS=backend,frontend,qa,architect,analyst,product_owner/" .env
  fi
fi

echo "=> 1. Generating Clean Config (v43)..."
bash generate-config.sh

echo "=> 2. REFRESHING INFRASTRUCTURE..."
docker compose down

echo "=> 🚨 Purging RAM Caches to free memory before relaunch..."
sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'

docker compose up -d

echo "=> 3. Stabilizing gateway and syncing ALL agent models (inc. CPU optimization)..."
sleep 20
bash pull-models.sh

echo "=> 4. FINAL Health-Check..."
for i in {1..10}; do
  STATUS=$(docker inspect -f '{{.State.Health.Status}}' openclaw-gateway 2>/dev/null || echo "starting")
  echo "Status: $STATUS ($i/10)"
  if [ "$STATUS" == "healthy" ]; then break; fi
  sleep 5
done

echo "=> 5. Applying QA Agent Execution Allowlist..."
docker exec openclaw-gateway openclaw approvals allowlist add --agent qa "*" || true

echo "=> 6. Re-launching Mission Control v43..."
pkill -f "mission_control.py" || true
pkill -f "run_mission_control.sh" || true
rm -f mission_logs.out
nohup python3 -u mission_control.py > mission_logs.out 2>&1 &

echo "=============================================================================="
echo "✅ MISSION: MULTI-MODEL PIPELINE COMPLETE (v43)"
echo "  Backend/Frontend → qwen2.5-coder:3b"
echo "  QA               → llama3.2:3b"
echo "  Architect/Analyst → qwen2.5:1.5b"
echo "=============================================================================="
tail -f mission_logs.out
