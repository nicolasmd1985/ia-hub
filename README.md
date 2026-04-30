# AI Development Hub — OpenClaw + Ollama (v43)

A 100% local, zero-cloud AI agent hub running on your machine with autonomous TDD capabilities.

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

## Architecture (Multi-Model Specialization)

The AI Hub utilizes specific models tailored for distinct agent roles to balance performance, memory, and reasoning precision:
- **Backend / Frontend Developers**: `qwen2.5-coder:3b`
- **Architect / Analyst (Routing & Planning)**: `qwen2.5:1.5b`
- **QA Engineer**: `llama3.2:3b`

These models are defined in `openclaw-docker/openclaw.json` and must be downloaded before executing the autonomous pipeline.

## Quick Start

```bash
# 1. Start Docker Infrastructure
make up

# 2. Pull all required multi-agent models (qwen & llama)
make pull-models

# 3. Open the Control UI (optional)
# -> http://localhost:18789
```

## Automated Kanban Workflow (Mission Control)

The AI Hub features a fully autonomous background daemon (`mission_control.py`) that syncs with your GitHub Project board to drive tasks automatically through the pipeline (To Do → In Progress → In Review QA → Pull Request Review).

### Enterprise Resilience:
- **SQLite Persistence**: Uses a local database (`mission_state.db`) to track recovery and hallucination limits between process restarts, preventing infinite API or Git loops.
- **Instance Locking**: Employs an OS-level file lock (`/tmp/mission_control.lock`) to ensure only one orchestrator daemon can run at a time, avoiding Git race conditions.
- **Strict QA Enforcement**: The QA agent cannot write data or hallucinate tools; it exclusively runs your test suite (`bash run_tests.sh`) and reports real terminal output back to the backend developer for iterative fixes.

### Running Mission Control

You can launch the orchestrator right from the Makefile, which also ensures logs are correctly truncated and mapped.

```bash
# Option 1: Run in foreground (watch output live)
make mission

# Option 2: Run in background (survives SSH disconnects)
nohup python3 -u mission_control.py > mission_logs.out 2>&1 &
```

### Managing the Daemon

**1. Watch live logs:**
```bash
make logs                # For Docker containers (Ollama/OpenClaw)
tail -f mission_logs.out # For Mission Control brain
```

**2. Stop Mission Control:**
```bash
pkill -f mission_control.py
```

**3. Nuclear Reset (Fresh Start):**
If the configuration breaks, or an agent hallucinates unrecoverable states inside the container, you can wipe the sessions, restore the gateway configs, and restart the daemon cleanly via:
```bash
bash apply_nuclear_patch.sh
```

## Useful Commands

| Command               | Action                               |
|-----------------------|--------------------------------------|
| `make up`             | Start all containers                 |
| `make down`           | Stop all containers                  |
| `make logs`           | Tail logs from containers            |
| `make status`         | Container + GPU + model status       |
| `make pull-models`    | Pull all required agent models       |
| `make mission`        | Start Mission Control orchestrator   |
| `make restart-openclaw` | Hot restart OpenClaw gateway       |
| `make purge-state`    | Forcefully clear session locks/jsonl |
| `make clean`          | Delete everything (including models) |

## GPU Passthrough

If `make status` shows GPU passthrough is NOT working, install the NVIDIA Container Toolkit:

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