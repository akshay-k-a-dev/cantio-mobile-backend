#!/bin/sh
set -e

echo "🔧 Starting Tailscale daemon..."
# Create directories
mkdir -p /var/run/tailscale /var/cache/tailscale /var/lib/tailscale

# Start tailscaled in background
tailscaled --state=/var/lib/tailscale/tailscaled.state --socket=/var/run/tailscale/tailscaled.sock &
sleep 3

if [ -z "$TAILSCALE_AUTHKEY" ]; then
    echo "❌ ERROR: TAILSCALE_AUTHKEY environment variable not set!"
    echo "   Set it in Leapcell dashboard as an environment variable"
    exit 1
fi

echo "🔐 Authenticating with Tailscale..."
tailscale up --authkey="${TAILSCALE_AUTHKEY}" --hostname=leapcell-proxy --accept-routes

echo "✅ Tailscale connected"
tailscale status

echo "🚀 Starting proxy server..."
exec python proxy_server.py
