#!/bin/bash
echo "--- DOCKER STATUS ---"
docker ps -a
docker compose ps
echo "--- LOGS LAST 20 ---"
docker logs --tail 20 openclaw-gateway
