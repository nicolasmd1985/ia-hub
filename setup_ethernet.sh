#!/bin/bash
# ============================================================================
#  CONFIGURE STATIC ETHERNET (Cable) — IP 192.168.1.90
#  
#  This script creates a NetworkManager connection profile for the
#  ethernet interface (eno1/enp2s0) with a fixed IP address.
#  
#  ⚠️  REQUIRES: sudo (must run as root or with sudo)
#  ⚠️  REQUIRES: Cable physically connected to the ethernet port
# ============================================================================
set -euo pipefail

ETH_DEVICE="eno1"
CONN_NAME="Cable-Fijo"
STATIC_IP="192.168.1.90"
GATEWAY="192.168.1.1"
DNS="8.8.8.8,1.1.1.1"
SUBNET_PREFIX="24"

echo "==================================================="
echo "🔌 Configuring Static Ethernet Connection"
echo "==================================================="
echo ""
echo "  Device:    $ETH_DEVICE"
echo "  IP:        $STATIC_IP/$SUBNET_PREFIX"
echo "  Gateway:   $GATEWAY"
echo "  DNS:       $DNS"
echo "  Profile:   $CONN_NAME"
echo ""

# ── 1. Check if running as root ──────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    echo "❌ This script must be run with sudo:"
    echo "   sudo bash $0"
    exit 1
fi

# ── 2. Check if cable is connected ──────────────────────────────────────────
CARRIER=$(cat /sys/class/net/$ETH_DEVICE/carrier 2>/dev/null || echo "0")
if [ "$CARRIER" != "1" ]; then
    echo "⚠️  WARNING: No cable detected on $ETH_DEVICE!"
    echo "   The connection profile will be created, but it won't"
    echo "   activate until you plug in the Ethernet cable."
    echo ""
fi

# ── 3. Delete existing connection if it exists ───────────────────────────────
if nmcli connection show "$CONN_NAME" &>/dev/null; then
    echo "🗑️  Removing old '$CONN_NAME' profile..."
    nmcli connection delete "$CONN_NAME"
fi

# Also remove the default auto-created "Wired connection 1"
if nmcli connection show "Wired connection 1" &>/dev/null; then
    echo "🗑️  Removing old 'Wired connection 1' profile..."
    nmcli connection delete "Wired connection 1"
fi

# ── 4. Create the new static connection ──────────────────────────────────────
echo "📝 Creating connection profile '$CONN_NAME'..."
nmcli connection add \
    type ethernet \
    con-name "$CONN_NAME" \
    ifname "$ETH_DEVICE" \
    ipv4.method manual \
    ipv4.addresses "${STATIC_IP}/${SUBNET_PREFIX}" \
    ipv4.gateway "$GATEWAY" \
    ipv4.dns "$DNS" \
    ipv6.method disabled \
    connection.autoconnect yes \
    connection.autoconnect-priority 100

# ── 5. Set ethernet as HIGHER PRIORITY than Wi-Fi ────────────────────────────
# Lower metric = higher priority. Default Wi-Fi is 600, we set ethernet to 100.
echo "⚡ Setting route priority (metric 100 = higher than Wi-Fi's 600)..."
nmcli connection modify "$CONN_NAME" ipv4.route-metric 100

# ── 6. Disable Wi-Fi power saving on the cable connection ────────────────────
# No power saving needed for wired connections, but ensure it's not inherited
nmcli connection modify "$CONN_NAME" 802-3-ethernet.wake-on-lan magic

# ── 7. Activate the connection ───────────────────────────────────────────────
if [ "$CARRIER" = "1" ]; then
    echo "🔌 Cable detected! Activating connection..."
    nmcli connection up "$CONN_NAME"
    
    echo ""
    echo "🔍 Verifying connectivity..."
    sleep 3
    
    ASSIGNED_IP=$(ip addr show $ETH_DEVICE | grep "inet " | awk '{print $2}')
    echo "  Assigned IP: $ASSIGNED_IP"
    
    if ping -c 1 -W 3 $GATEWAY &>/dev/null; then
        echo "  ✅ Gateway reachable"
    else
        echo "  ❌ Gateway NOT reachable — check cable/router"
    fi
    
    if ping -c 1 -W 3 8.8.8.8 &>/dev/null; then
        echo "  ✅ Internet reachable"
    else
        echo "  ❌ Internet NOT reachable — check router WAN"
    fi
    
    if host api.github.com &>/dev/null; then
        echo "  ✅ DNS working (api.github.com resolved)"
    else
        echo "  ⚠️  DNS not resolving yet (may take a moment)"
    fi
else
    echo "⏳ Connection profile created but NOT activated (no cable)."
    echo "   Plug in the Ethernet cable and it will auto-connect."
fi

# ── 8. Summary ───────────────────────────────────────────────────────────────
echo ""
echo "==================================================="
echo "✅ ETHERNET CONFIGURATION COMPLETE"
echo ""
echo "Profile '$CONN_NAME' has been created with:"
echo "  • Static IP:     $STATIC_IP"
echo "  • Gateway:       $GATEWAY"  
echo "  • DNS:           $DNS"
echo "  • Auto-connect:  YES (priority over Wi-Fi)"
echo "  • Route metric:  100 (Wi-Fi is 600 — cable always wins)"
echo ""
echo "📌 SSH will always be available at:"
echo "   ssh nicolasmd@$STATIC_IP"
echo ""
echo "💡 If the IP is taken, edit this script and change STATIC_IP."
echo "   Run again with: sudo bash $0"
echo "==================================================="
