# Phone Server Proxy via GitHub Actions

This setup allows you to expose your phone server (running on Tailscale) to the public internet using GitHub Actions + Cloudflare Tunnel.

## Architecture

```
User Request → Cloudflare Tunnel → GitHub Actions Proxy → Tailscale → Phone Server (100.87.250.20:8081)
```

## Prerequisites

### 1. Phone Server Running

On your phone (Termux), start the backend:

```bash
cd ~/backend
python -m uvicorn main:app --host 0.0.0.0 --port 8081
```

Leave this running. It will serve all yt-dlp supported platforms.

### 2. Phone Connected to Tailscale

Make sure your phone is connected to Tailscale with IP `100.87.250.20`.

### 3. GitHub Secrets Setup

Go to your repository settings → Secrets and variables → Actions

Add these secrets:

- `TS_OAUTH_CLIENT_ID`: Your Tailscale OAuth Client ID
- `TS_OAUTH_SECRET`: Your Tailscale OAuth Secret

To get OAuth credentials:
1. Go to https://login.tailscale.com/admin/settings/oauth
2. Generate OAuth Client
3. Add tag `tag:ci` to the ACL if needed

## Usage

### Start the Proxy

1. Go to: https://github.com/akshay-k-a-dev/cantio-mobile-backend/actions
2. Click "Phone Server Proxy" workflow
3. Click "Run workflow" → "Run workflow"

### Get the URL

1. Click on the running workflow
2. Look in the "Setup Cloudflare Tunnel" step logs
3. Find a line like: `https://random-words.trycloudflare.com`
4. Use that URL to access your phone server

Example:
```bash
curl "https://your-tunnel.trycloudflare.com/stream?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

## Features

- ✅ Auto-restart every 30 minutes (keeps tunnel alive)
- ✅ Runs for up to 6 hours per job
- ✅ CORS enabled for all origins
- ✅ Full request/response proxying
- ✅ Health check monitoring every 5 minutes

## Supported Platforms

Your phone server now supports **1800+ platforms**:
- YouTube / YouTube Music
- SoundCloud
- Vimeo
- TikTok
- Twitter/X
- Instagram
- Twitch
- And many more!

## Troubleshooting

### Tunnel URL not showing?

Check the "Setup Cloudflare Tunnel" step logs carefully. The URL appears within the first 10 seconds.

### Phone unreachable?

1. Verify phone server is running on port 8081
2. Check Tailscale connection on phone: `tailscale status`
3. Verify phone IP is `100.87.250.20`

### Workflow stops after 30 minutes?

The cron schedule automatically restarts it. The Cloudflare URL will change each time.

### Want a stable URL?

You'll need one of these:
- Custom domain with Cloudflare Tunnel (paid)
- ngrok with reserved domain (paid)
- Set up dynamic DNS and update GitHub Gist with current URL

## Notes

- **URL changes every restart** - that's how free Cloudflare Tunnels work
- The workflow uses GitHub Actions free tier (2000 minutes/month)
- Phone must stay connected to Tailscale
- Phone must have backend server running on port 8081
