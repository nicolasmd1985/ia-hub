#!/bin/bash
# AI Development Hub - Extreme Swap Setup Script
# This script creates a 32GB swap file to support 7B models on CPU hardware.
# WARNING: This requires 32GB of free disk space.

SWAP_FILE="/swapfile"
SWAP_SIZE="32G"

echo "--- Endurance Mode: Initiating 32GB Swap Creation ---"

if [ -f "$SWAP_FILE" ]; then
    echo "Found existing swapfile. Disabling..."
    sudo swapoff "$SWAP_FILE"
    sudo rm "$SWAP_FILE"
fi

echo "Allocating $SWAP_SIZE for $SWAP_FILE (this may take a minute)..."
sudo fallocate -l "$SWAP_SIZE" "$SWAP_FILE" || sudo dd if=/dev/zero of="$SWAP_FILE" bs=1G count=32

echo "Setting permissions..."
sudo chmod 600 "$SWAP_FILE"

echo "Formatting swap..."
sudo mkswap "$SWAP_FILE"

echo "Enabling swap..."
sudo swapon "$SWAP_FILE"

# Add to fstab if not already present
if ! grep -q "$SWAP_FILE" /etc/fstab; then
    echo "Adding entry to /etc/fstab..."
    echo "$SWAP_FILE none swap sw 0 0" | sudo tee -a /etc/fstab
fi

echo "--- COMPLETE ---"
free -h
echo "Endurance Mode: OS is ready for memory-intensive modeling."
