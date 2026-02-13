# GitHub Actions Proxy Setup

## Overview

This uses GitHub Actions as a persistent proxy that:
1. Connects to your phone via Tailscale
2. Proxies requests from Leapcell to your phone
3. Exposes itself via Cloudflare Tunnel

## Setup Steps

### 1. Create Tailscale OAuth Client

Go to https://login.tailscale.com/admin/settings/oauth

1. Click **Generate OAuth client**
2. Add tags: `tag:ci`
3. Copy the **Client ID** and **Client Secret**

### 2. Add GitHub Secrets

In your GitHub repo: Settings → Secrets and variables → Actions

Add these secrets:
```
TAILSCALE_OAUTH_CLIENT_ID=<your-client-id>
TAILSCALE_OAUTH_SECRET=<your-client-secret>
```

### 3. Configure ACL for CI tag

In Tailscale Admin → Access Controls, add:

```json
{
  "tagOwners": {
    "tag:ci": ["autogroup:admin"]
  },
  "acls": [
    {
      "action": "accept",
      "src": ["tag:ci"],
      "dst": ["*:*"]
    }
  ]
}
```

### 4. Start Phone Backend

On your phone (Termux):
```bash
cd cantio-mobile-backend
python -m uvicorn main:app --host 0.0.0.0 --port 8081
```

### 5. Run GitHub Action

1. Go to your repo → Actions tab
2. Click "Phone Proxy via Tailscale"
3. Click "Run workflow"
4. Wait ~30 seconds
5. Open the workflow run logs
6. Find the **Cloudflare Tunnel URL** in the logs (e.g., `https://xyz.trycloudflare.com`)

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
