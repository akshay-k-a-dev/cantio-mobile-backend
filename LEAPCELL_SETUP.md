# Leapcell Deployment Setup

## 1. Generate Tailscale Auth Key

Go to https://login.tailscale.com/admin/settings/keys

1. Click **Generate auth key**
2. Settings:
   - **Reusable**: ✅ (so container restarts work)
   - **Ephemeral**: ✅ (removes node when container stops)
   - **Expiration**: Set to 90 days or longer
3. Copy the auth key (starts with `tskey-auth-...`)

## 2. Configure Leapcell Environment Variables

In your Leapcell project dashboard:

1. Go to **Settings** → **Environment Variables**
2. Add these variables:

```
TAILSCALE_AUTHKEY=tskey-auth-xxxxxxxxxxxxxxxxxxxxxxxxxxxxx
PHONE_IP=100.87.250.20
PHONE_PORT=8081
SKIP_CHECKS=true
```

## 3. Deploy

Push your code to trigger a new deployment. The container will:

1. ✅ Install Tailscale
2. ✅ Connect to your tailnet using the auth key
3. ✅ Connect to your phone at `100.87.250.20:8081`
4. ✅ Start proxying requests

## 4. Verify Connection

Check the deployment logs for:
```
✅ Tailscale connected
🚀 Starting proxy server...
🔄 Proxying 0.0.0.0:8080 → http://100.87.250.20:8081
```

Then test:
```bash
curl https://your-leapcell-app.com/kaithhealthcheck
```

## Troubleshooting

**Error: TAILSCALE_AUTHKEY not set**
- Make sure you added the environment variable in Leapcell dashboard

**Container can't reach phone**
- Verify phone backend is running: `python -m uvicorn main:app --host 0.0.0.0 --port 8081`
- Check phone's Tailscale IP: Open Tailscale app
- Test from phone: `curl http://100.87.250.20:8081/kaithhealthcheck`

**Tailscale auth fails**
- Generate a new auth key (they expire)
- Make sure "Reusable" is checked when generating
