#!/bin/bash
# AI Development Hub - Extreme Swap Setup Script (BTRFS COMPATIBLE)
# Btrfs requires "NOCOW" (+C) attribute BEFORE allocating space.

SWAP_FILE="/swapfile"
SWAP_SIZE="32G"

echo "--- Endurance Mode: Initiating 32GB Swap Creation (Btrfs detected) ---"

# 1. Clean up old attempt
if [ -f "$SWAP_FILE" ]; then
    echo "Cleaning up previous failed swapfile..."
    sudo swapoff "$SWAP_FILE" 2>/dev/null
    sudo rm -f "$SWAP_FILE"
fi

# 2. Create a 0-length file and set NOCOW Attribute
# This MUST be done before allocating any data to the file on Btrfs.
echo "Initializing NOCOW attribute..."
sudo touch "$SWAP_FILE"
sudo chattr +C "$SWAP_FILE"

# 3. Use dd to allocate. Do NOT use fallocate on Btrfs for swap.
echo "Allocating $SWAP_SIZE (using dd - this will take about 1 minute)..."
sudo dd if=/dev/zero of="$SWAP_FILE" bs=1G count=32 status=progress

# 4. Set permissions
echo "Setting permissions..."
sudo chmod 600 "$SWAP_FILE"

# 5. Format and Enable
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
echo "Endurance Mode: OS is Btrfs-optimized and ready."
