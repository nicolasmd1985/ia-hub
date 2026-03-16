#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  GPU + Docker preflight check for AI Development Hub
#  Run this BEFORE `make up` to validate your environment
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

ok()   { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
fail() { echo -e "${RED}[✗]${NC} $1"; }
info() { echo -e "${BLUE}[i]${NC} $1"; }

echo ""
echo "═══════════════════════════════════════════════════"
echo "   AI Hub — GPU & Docker Environment Check"
echo "═══════════════════════════════════════════════════"
echo ""

# ── Docker ────────────────────────────────────────────
info "Checking Docker..."
if docker info &>/dev/null; then
    DOCKER_VER=$(docker --version | awk '{print $3}' | tr -d ',')
    ok "Docker running (v${DOCKER_VER})"
else
    fail "Docker is not running. Start Docker and retry."
    exit 1
fi

# Docker Compose
if docker compose version &>/dev/null; then
    COMPOSE_VER=$(docker compose version --short 2>/dev/null || echo "v2+")
    ok "Docker Compose available (${COMPOSE_VER})"
else
    fail "Docker Compose v2 not found. Install it: https://docs.docker.com/compose/install/"
    exit 1
fi

# ── GPU / NVIDIA ───────────────────────────────────────
echo ""
info "Checking GPU..."

if command -v nvidia-smi &>/dev/null; then
    ok "nvidia-smi found"
    echo ""
    nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader | \
        while IFS=',' read -r name mem drv; do
            ok "GPU: ${name} | VRAM: ${mem} | Driver: ${drv}"
        done
    echo ""

    # NVIDIA Container Toolkit
    if docker run --rm --gpus all nvidia/cuda:12.3.0-base-ubuntu22.04 nvidia-smi &>/dev/null; then
        ok "NVIDIA Container Toolkit working (GPU passthrough verified!)"
    else
        warn "GPU passthrough NOT working. Install NVIDIA Container Toolkit:"

        # Detect OS family
        OS_ID=$(. /etc/os-release 2>/dev/null && echo "${ID:-unknown}" || echo "unknown")

        case "$OS_ID" in
            fedora|rhel|centos|rocky|almalinux)
                warn "Detected: Fedora/RHEL — run these commands:"
                echo "      curl -s -L https://nvidia.github.io/libnvidia-container/stable/rpm/nvidia-container-toolkit.repo \\"
                echo "        | sudo tee /etc/yum.repos.d/nvidia-container-toolkit.repo"
                echo "      sudo dnf install -y nvidia-container-toolkit"
                echo "      sudo nvidia-ctk runtime configure --runtime=docker"
                echo "      sudo systemctl restart docker"
                ;;
            ubuntu|debian|linuxmint|pop)
                warn "Detected: Debian/Ubuntu — run these commands:"
                echo "      sudo mkdir -p /usr/share/keyrings"
                echo "      curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg"
                echo "      curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list"
                echo "      sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit"
                echo "      sudo nvidia-ctk runtime configure --runtime=docker"
                echo "      sudo systemctl restart docker"
                ;;
            *)
                warn "Unknown distro — see: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
                ;;
        esac
    fi
else
    warn "nvidia-smi not found — running CPU-only mode"
    warn "Ollama will use CPU inference (slower but functional)"
    warn "If you have a GPU, install NVIDIA drivers: https://www.nvidia.com/drivers"
fi

# ── RAM ────────────────────────────────────────────────
echo ""
info "Checking RAM..."
TOTAL_RAM=$(free -g | awk '/^Mem:/{print $2}')
AVAIL_RAM=$(free -g | awk '/^Mem:/{print $7}')
ok "Total RAM: ${TOTAL_RAM}GB | Available: ${AVAIL_RAM}GB"
if [ "$TOTAL_RAM" -ge 8 ]; then
    ok "RAM sufficient for local LLM inference"
else
    warn "Less than 8GB RAM — consider smaller models (e.g., phi3:mini)"
fi

# ── Network ────────────────────────────────────────────
echo ""
info "Checking Docker network..."
if docker network ls | grep -q "ai-brain-net"; then
    ok "Internal network 'ai-brain-net' already exists"
else
    info "Network 'ai-brain-net' will be created on first 'make up'"
fi

# ── .env ───────────────────────────────────────────────
echo ""
info "Checking .env file..."
if [ -f ".env" ]; then
    ok ".env file found"
    if grep -q "change-me" .env; then
        warn "OPENCLAW_GATEWAY_TOKEN is still the default — change it in .env!"
    fi
else
    warn ".env not found — copying from .env.example"
    cp .env.example .env
    ok "Created .env from .env.example — edit it now!"
fi

echo ""
echo "═══════════════════════════════════════════════════"
echo "  All checks done! Run: make up"
echo "═══════════════════════════════════════════════════"
echo ""
