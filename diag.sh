#!/bin/bash
echo "--- SYSTEM STATUS ---"
date
uptime
df -h /
free -m
ps aux | grep -v grep | grep -E "python3|bash|ollama|openclaw"
ls -lt mission_logs*
echo "--- HUB DIR ---"
ls -a
