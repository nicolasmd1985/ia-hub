#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  Pull all required open-source models into Ollama
#  Run after `make up` to download models for all agents
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

ok()   { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
info() { echo -e "${BLUE}[→]${NC} $1"; }
fail() { echo -e "${RED}[✗]${NC} $1"; }

# ── Agent → Model mapping ────────────────────────────────────────────────────
declare -A AGENT_MODELS=(
  ["general"]="qwen2.5:7b"
  ["fast"]="qwen2.5:3b"
  ["coder"]="qwen2.5-coder:7b"
  ["reasoner"]="deepseek-r1:7b"
  ["analyst"]="qwen2.5:3b"
)

# ── Check Ollama is running ──────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════"
echo "   Pulling models for all AI Hub agents"
echo "═══════════════════════════════════════════════════"
echo ""

OLLAMA_STATUS=$(docker inspect --format='{{.State.Status}}' ollama-brain 2>/dev/null || echo "not found")
if [ "$OLLAMA_STATUS" != "running" ]; then
    fail "Ollama container is not running (status: ${OLLAMA_STATUS}). Run 'make up' first."
    exit 1
fi

ok "Ollama is running"
echo ""

# ── Pull each model ──────────────────────────────────────────────────────────
FAILED=()

for agent in "${!AGENT_MODELS[@]}"; do
    model="${AGENT_MODELS[$agent]}"
    echo "────────────────────────────────────────────"
    info "Agent: ${agent}  →  Model: ${model}"
    echo ""

    if docker exec ollama-brain ollama pull "$model"; then
        ok "Pulled: $model"
    else
        warn "Failed to pull: $model  (will retry or skip)"
        FAILED+=("$model")
    fi
    echo ""
done

# ── Summary ──────────────────────────────────────────────────────────────────
echo "═══════════════════════════════════════════════════"
echo "  Download complete. Installed models:"
echo "═══════════════════════════════════════════════════"
docker exec ollama-brain ollama list
echo ""

if [ ${#FAILED[@]} -gt 0 ]; then
    warn "These models failed to pull:"
    for m in "${FAILED[@]}"; do
        echo "  - $m"
    done
    echo ""
    warn "Try pulling manually: docker exec ollama-brain ollama pull <model>"
else
    ok "All models pulled successfully!"
    echo ""
    echo "  Run the test suite: bash test-hub.sh"
fi
