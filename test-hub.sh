#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  AI Hub Integration Test Suite
#  Tests all services, models, and agent routing end-to-end
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

ok()   { echo -e "  ${GREEN}[PASS]${NC} $1"; PASSES=$((PASSES+1)); }
fail() { echo -e "  ${RED}[FAIL]${NC} $1"; FAILS=$((FAILS+1)); }
warn() { echo -e "  ${YELLOW}[SKIP]${NC} $1"; }
info() { echo -e "${BLUE}[TEST]${NC} $1"; }
section() { echo ""; echo -e "${CYAN}━━━ $1 ━━━${NC}"; }

PASSES=0
FAILS=0

# ── Config ───────────────────────────────────────────────────────────────────
OLLAMA_URL="http://localhost:11434"
OPENCLAW_URL="http://localhost:18789"
GATEWAY_TOKEN="${OPENCLAW_GATEWAY_TOKEN:-local-dev-token-change-me}"

declare -A AGENT_MODELS=(
  ["general"]="qwen2.5:7b"
  ["fast"]="qwen2.5:3b"
  ["coder"]="qwen2.5-coder:7b"
  ["reasoner"]="deepseek-r1:7b"
  ["analyst"]="qwen2.5:3b"
)

# Test prompts per agent (short so tests are fast)
declare -A AGENT_PROMPTS=(
  ["general"]="In one sentence, what is Docker?"
  ["fast"]="What is 2+2?"
  ["coder"]="Write a one-line Python function that returns the square of a number."
  ["reasoner"]="What is the next number in the sequence: 2, 4, 8, 16? Explain briefly."
  ["analyst"]="In two sentences, what makes a good software architecture?"
)

echo ""
echo "═══════════════════════════════════════════════════════"
echo "   AI Development Hub — Integration Test Suite"
echo "═══════════════════════════════════════════════════════"

# ════════════════════════════════════════════════════════
# TEST 1: Docker containers running
# ════════════════════════════════════════════════════════
section "1. Docker Container Status"

for container in ollama-brain openclaw-gateway; do
    STATUS=$(docker inspect --format='{{.State.Status}}' "$container" 2>/dev/null || echo "not found")
    if [ "$STATUS" = "running" ]; then
        ok "Container '$container' is running"
    else
        fail "Container '$container' — status: $STATUS (run 'make up')"
    fi
done

# ════════════════════════════════════════════════════════
# TEST 2: Ollama API health
# ════════════════════════════════════════════════════════
section "2. Ollama API Health"

OLLAMA_RESP=$(curl -sf "${OLLAMA_URL}/api/tags" 2>/dev/null)
if [ $? -eq 0 ] && echo "$OLLAMA_RESP" | grep -q "models"; then
    ok "Ollama API is responding at ${OLLAMA_URL}"
else
    fail "Ollama API not reachable at ${OLLAMA_URL}"
fi

# ════════════════════════════════════════════════════════
# TEST 3: Models downloaded
# ════════════════════════════════════════════════════════
section "3. Model Availability in Ollama"

DOWNLOADED_MODELS=$(curl -sf "${OLLAMA_URL}/api/tags" 2>/dev/null | grep -o '"name":"[^"]*"' | sed 's/"name":"//;s/"//' || echo "")

for agent in "${!AGENT_MODELS[@]}"; do
    model="${AGENT_MODELS[$agent]}"
    # Check model name without tag as fallback too
    model_base="${model%%:*}"
    if echo "$DOWNLOADED_MODELS" | grep -q "$model_base"; then
        ok "Model '$model' found (agent: $agent)"
    else
        fail "Model '$model' NOT found — run: docker exec ollama-brain ollama pull $model"
    fi
done

# ════════════════════════════════════════════════════════
# TEST 4: Internal network reachability (OpenClaw → Ollama)
# ════════════════════════════════════════════════════════
section "4. Internal Network (OpenClaw → Ollama via ai-brain-net)"

# Use curl — OpenClaw is Node/Debian and has curl (installed in Dockerfile)
if docker exec openclaw-gateway curl -sf http://ollama-brain:11434/api/tags > /dev/null 2>&1; then
    ok "OpenClaw container can reach Ollama at http://ollama-brain:11434"
else
    fail "OpenClaw CANNOT reach Ollama via internal network"
fi

# ════════════════════════════════════════════════════════
# TEST 5: OpenClaw Gateway health
# ════════════════════════════════════════════════════════
section "5. OpenClaw Gateway Health"

OC_STATUS=$(curl -sf -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer ${GATEWAY_TOKEN}" \
    "${OPENCLAW_URL}/health" 2>/dev/null || echo "000")

if [ "$OC_STATUS" = "200" ]; then
    ok "OpenClaw Gateway healthy (HTTP 200)"
elif [ "$OC_STATUS" = "401" ]; then
    fail "OpenClaw returned 401 — wrong OPENCLAW_GATEWAY_TOKEN in .env"
elif [ "$OC_STATUS" = "000" ]; then
    fail "OpenClaw Gateway not reachable at ${OPENCLAW_URL}"
else
    warn "OpenClaw returned HTTP $OC_STATUS (may still be starting up)"
fi

# ════════════════════════════════════════════════════════
# TEST 6: GPU passthrough check
# ════════════════════════════════════════════════════════
section "6. GPU Passthrough in Ollama Container"

# Run nvidia-smi silently — capture nothing, just check exit code
if docker exec ollama-brain sh -c 'nvidia-smi > /dev/null 2>&1'; then
    GPU_NAME=$(docker exec ollama-brain sh -c 'nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null' || echo "unknown")
    ok "GPU passthrough working: $GPU_NAME"
else
    warn "No GPU passthrough (CPU mode — install NVIDIA Container Toolkit + run 'make up-gpu')"
fi

# ════════════════════════════════════════════════════════
# TEST 7: Live inference — ping each agent model
# ════════════════════════════════════════════════════════
section "7. Live Inference per Agent (Direct Ollama API)"

echo "  Running quick inference test on each model..."
echo "  (This may take 1-3 min per model on first run)"
echo ""

for agent in "${!AGENT_MODELS[@]}"; do
    model="${AGENT_MODELS[$agent]}"
    prompt="${AGENT_PROMPTS[$agent]}"

    echo -e "  ${BLUE}→${NC} Testing agent '$agent' with model '$model'..."

    RESPONSE=$(curl -sf "${OLLAMA_URL}/api/generate" \
        -H "Content-Type: application/json" \
        -d "{
            \"model\": \"${model}\",
            \"prompt\": \"${prompt}\",
            \"stream\": false,
            \"options\": { \"num_predict\": 50 }
        }" 2>/dev/null)

    if echo "$RESPONSE" | grep -q '"response"'; then
        ANSWER=$(echo "$RESPONSE" | grep -o '"response":"[^"]*"' | sed 's/"response":"//;s/"//' | head -c 100)
        ok "Agent '$agent' ($model): \"${ANSWER}...\""
    else
        fail "Agent '$agent' ($model) — no response (model loaded?)"
    fi
    echo ""
done

# ════════════════════════════════════════════════════════
# RESULTS SUMMARY
# ════════════════════════════════════════════════════════
TOTAL=$((PASSES + FAILS))
echo ""
echo "═══════════════════════════════════════════════════════"
printf " Results: ${GREEN}%d PASSED${NC} | ${RED}%d FAILED${NC} | %d TOTAL\n" \
    "$PASSES" "$FAILS" "$TOTAL"
echo "═══════════════════════════════════════════════════════"
echo ""

if [ "$FAILS" -eq 0 ]; then
    echo -e "${GREEN}  ✓ All tests passed! AI Hub is fully operational.${NC}"
    echo ""
    echo "  Control UI  → http://localhost:18789"
    echo "  Ollama API  → http://localhost:11434"
else
    echo -e "${YELLOW}  Some tests failed. Check the output above for details.${NC}"
    echo ""
    echo "  Common fixes:"
    echo "    Containers down?  → make up"
    echo "    Models missing?   → bash pull-models.sh"
    echo "    GPU not working?  → bash check-env.sh"
fi
echo ""

# Exit with failure code if any tests failed
exit $FAILS
