# GitHub Actions Proxy Setup

## Overview

This uses GitHub Actions as a persistent proxy that:
1. Connects to your phone via Tailscale
2. Proxies requests from Leapcell to your phone
3. Exposes itself via Cloudflare Tunnel

## Setup Steps

### 1. Use Your Existing Tailscale Auth Key

You already have a Tailscale auth key (starts with `tskey-auth-...`).

### 2. Add GitHub Secret

In your GitHub repo: Settings → Secrets and variables → Actions

Add this secret:
```
TAILSCALE_AUTHKEY=tskey-auth-xxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

(Use the same auth key you have)

### 3. Start Phone Backend

On your phone (Termux):
```bash
cd cantio-mobile-backend
python -m uvicorn main:app --host 0.0.0.0 --port 8081
```

### 4. Run GitHub Action

1. Go to your repo → Actions tab
2. Click "Phone Proxy via Tailscale"
3. Click "Run workflow"
4. Wait ~30 seconds
5. Open the workflow run logs
6. F5nd the **Cloudflare Tunnel URL** in the logs (e.g., `https://xyz.trycloudflare.com`)

### 6. Update Leapcell

Set environment variable in Leapcell:
```
BACKEND_URL=https://xyz.trycloudflare.com
```

Then update your Leapcell deployment to proxy to this URL.

## How It Works

```
User Request
    ↓
Leapcell (serverless)
    ↓ HTTPS
Cloudflare Tunnel URL (public)
    ↓
GitHub Actions Runner (proxy)
    ↓ Tailscale
Phone (100.87.250.20:8081)
    ↓ Residential IP
YouTube
```

## Limitations

- GitHub Actions jobs run for max 6 hours
- The workflow auto-restarts every 30 minutes
- Cloudflare tunnel URL changes on each run (you'll need to update it)

## Alternative: Static Tunnel

For a stable URL, use Cloudflare Named Tunnels:
1. Create a tunnel: `cloudflared tunnel create gh-proxy`
2. Add the tunnel credentials to GitHub Secrets
3. Update the workflow to use named tunnel with your domain

## Troubleshooting

**"Phone not reachable"**
- Verify phone backend is running on port 8081
- Check phone's Tailscale app is connected
- Verify IP is 100.87.250.20 in Tailscale app

**"Tunnel not starting"**
- Check Actions logs for errors
- May need to wait 10-20 seconds for tunnel to establish

**"Connection timeout"**
- GitHub Actions may have network restrictions
- Try running workflow again
