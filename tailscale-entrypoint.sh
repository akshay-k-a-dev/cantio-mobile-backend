#!/bin/sh
set -e

echo "🔧 Starting Tailscale daemon..."
# Create directories
mkdir -p /var/run/tailscale /var/cache/tailscale /var/lib/tailscale

# Start tailscaled in background (no sudo needed in Docker)
/usr/sbin/tailscaled --state=/var/lib/tailscale/tailscaled.state --socket=/var/run/tailscale/tailscaled.sock &
sleep 5

if [ -z "$TAILSCALE_AUTHKEY" ]; then
    echo "❌ ERROR: TAILSCALE_AUTHKEY environment variable not set!"
    echo "   Set it in Leapcell dashboard as an environment variable"
    exit 1
fi

echo "🔐 Authenticating with Tailscale..."
/usr/bin/tailscale up --authkey="${TAILSCALE_AUTHKEY}" --hostname=leapcell-proxy --accept-routes

echo "✅ Tailscale connected"
/usr/bin/tailscale status

echo "🔍 Testing connection to phone..."
if ping -c 1 -W 2 ${PHONE_IP}; then
    echo "✅ Phone ${PHONE_IP} is reachable"
else
    echo "⚠️  Cannot ping ${PHONE_IP}, but continuing anyway..."
fi

echo "🚀 Starting proxy server..."
exec python proxy_server.py
