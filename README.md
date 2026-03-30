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

## Automated Kanban Workflow (Mission Control)

The AI Hub features a fully autonomous background daemon (`mission_control.py`) that syncs with your GitHub Project board to drive tasks automatically.

### Running Mission Control in the Background

Since the python script has an internal continuous loop (polling every 15s), you can use the `run_mission_control.sh` wrapper combined with `nohup` to run it indefinitely as a background service:

```bash
nohup ./run_mission_control.sh > mission_logs.out 2>&1 &
```

**What this does:**
1. **Detaches** the process from your terminal, allowing it to survive server disconnects or window closures.
2. Uses the bash wrapper (`run_mission_control.sh`) as a safety **watchdog** that automatically restarts the python script if it ever fatally crashes.
3. Redirects all logs (standard outputs + errors) to the `mission_logs.out` file.

### Managing the Background Process

**1. Watch the live logs:**
```bash
tail -f mission_logs.out
```
*(Press `Ctrl+C` to stop watching. The script will safely continue running in the background).*

**2. Check if the loop is actively running:**
```bash
ps aux | grep mission_control
```
*(Note: If the only result you see is `grep --color=auto mission_control`, it means the background daemon is OFF. That line is just the terminal capturing your search command executing at that exact millisecond).*

**3. Stop the background process entirely:**
```bash
pkill -f mission_control.py && pkill -f run_mission_control.sh
```
*(You must kill both to stop the system completely. The python process runs the logic, while the bash script runs the watchdog wrapping it. Killing only one might trigger the other to auto-restart).*
