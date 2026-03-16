# ─────────────────────────────────────────────────────────────────────────────
#  AI Development Hub — Makefile
#  Usage: make <target>
# ─────────────────────────────────────────────────────────────────────────────

.PHONY: help check up down logs pull model models pull-models test status shell-ollama shell-openclaw clean

# Default model to pull
MODEL ?= llama3.2:latest

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

check: ## Run preflight GPU + Docker check
	@bash check-env.sh

up: ## Start the full AI Hub in CPU mode (no GPU required)
	@cp -n .env.example .env 2>/dev/null || true
	@bash generate-config.sh
	docker compose up -d --build
	@echo ""
	@echo "✓ AI Hub started (CPU mode)!"
	@echo "  → OpenClaw Control UI: http://localhost:18789"
	@echo "  → Ollama API:          http://localhost:11434"
	@echo ""
	@echo "Pull your first model: make pull-models"

up-gpu: ## Start with GPU passthrough (requires NVIDIA Container Toolkit)
	@cp -n .env.example .env 2>/dev/null || true
	@bash generate-config.sh
	docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
	@echo ""
	@echo "✓ AI Hub started (GPU mode)!"
	@echo "  → OpenClaw Control UI: http://localhost:18789"
	@echo "  → Ollama API:          http://localhost:11434"

down: ## Stop all containers
	docker compose down

logs: ## Tail logs from all containers
	docker compose logs -f

logs-ollama: ## Tail Ollama logs only
	docker compose logs -f ollama-brain

logs-openclaw: ## Tail OpenClaw logs only
	docker compose logs -f openclaw-gateway

pull: ## Pull latest Docker images
	docker compose pull

models: pull-models ## Alias for pull-models

pull-models: ## Pull ALL agent models (qwen2.5, qwen2.5-coder, deepseek-r1, kimi-k2.5)
	bash pull-models.sh

model: ## Pull a single model (set MODEL=name:tag)
	@echo "Pulling model: $(MODEL)"
	docker exec ollama-brain ollama pull $(MODEL)

model-list: ## List all downloaded models
	docker exec ollama-brain ollama list

test: ## Run full integration test suite
	bash test-hub.sh

status: ## Show container status and GPU usage
	@echo "=== Container Status ==="
	docker compose ps
	@echo ""
	@echo "=== GPU Status ==="
	@docker exec ollama-brain nvidia-smi 2>/dev/null || echo "GPU not available / no NVIDIA driver"
	@echo ""
	@echo "=== Ollama Models ==="
	docker exec ollama-brain ollama list 2>/dev/null || echo "Ollama not ready yet"

shell-ollama: ## Open shell inside Ollama container
	docker exec -it ollama-brain bash

shell-openclaw: ## Open shell inside OpenClaw container
	docker exec -it openclaw-gateway bash

restart-openclaw: ## Restart only OpenClaw (without touching Ollama)
	docker compose restart openclaw-gateway

restart-ollama: ## Restart only Ollama (keeps models loaded if possible)
	docker compose restart ollama-brain

clean: ## Remove all containers, networks, and volumes (WARNING: deletes models!)
	@echo "WARNING: This will delete all downloaded models and state!"
	@read -p "Are you sure? [y/N] " c; [ "$$c" = "y" ] && docker compose down -v || echo "Aborted."
