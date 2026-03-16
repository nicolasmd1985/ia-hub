# AI Development Hub — OpenClaw + Ollama

A 100% local, zero-cloud AI agent hub running on your machine.

```
┌─────────────────────────────────────────────────────┐
│                  ai-brain-net (bridge)               │
│                                                      │
│  ┌──────────────────┐    ┌──────────────────────┐   │
│  │  openclaw-gateway │───▶│   ollama-brain       │   │
│  │  :18789 (UI/API) │    │   :11434 (inference) │   │
│  │  Agent routing   │    │   GPU passthrough    │   │
│  └──────────────────┘    └──────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

## Quick Start

```bash
# 1. Preflight check (GPU, Docker, RAM)
make check

# 2. Start everything
make up

# 3. Pull your first model (llama3.2 default)
make model

# 4. Open the Control UI
open http://localhost:18789
```

## Using a different model

```bash
make model MODEL=codellama:latest
make model MODEL=mistral:latest
make model MODEL=deepseek-coder:latest
```

## Useful commands

| Command               | Action                               |
|-----------------------|--------------------------------------|
| `make up`             | Start all containers                 |
| `make down`           | Stop all containers                  |
| `make logs`           | Tail logs from everything            |
| `make status`         | Container + GPU + model status       |
| `make model-list`     | List downloaded models               |
| `make restart-openclaw` | Hot restart OpenClaw only          |
| `make restart-ollama` | Hot restart Ollama only              |
| `make clean`          | Delete everything (including models) |

## Configuration

Edit `openclaw-docker/openclaw.json` to:
- Add/remove models from the Ollama provider
- Set the default agent model
- Customize agent system prompts
- Add new agent profiles (e.g., `coder`, `researcher`)

Edit `.env` to change the gateway auth token.

## GPU Passthrough

If `make check` shows GPU passthrough is NOT working, install NVIDIA Container Toolkit:

```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

Then run `make check` again to verify.

## Architecture

- **ollama-brain**: Ollama inference engine, GPU-accelerated, models cached in named volume
- **openclaw-gateway**: OpenClaw agent gateway, built from Node 22 + npm package
- **ai-brain-net**: Internal Docker bridge — OpenClaw reaches Ollama at `http://ollama-brain:11434`
- Both containers restart automatically unless explicitly stopped
