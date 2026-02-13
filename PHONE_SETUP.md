# Phone Backend + Cloud Proxy Setup

## Architecture
```
Internet → Cloud Server (public) → Tailscale → Phone (residential IP) → YouTube
```

## Setup Instructions

### 1. Phone Setup (Termux)

Install Termux from F-Droid, then:

```bash
# Install dependencies
pkg update && pkg upgrade
pkg install python git

# Clone repo
git clone https://github.com/akshay-k-a-dev/cantio-mobile-backend.git
cd cantio-mobile-backend

# Install Python packages
pip install -r requirements.txt

# Run backend on port 8081 (keep this running)
python -m uvicorn main:app --host 0.0.0.0 --port 8081
```

**Get your phone's Tailscale IP:**
- Open Tailscale app
- Note the IP (e.g., `100.64.1.2`)

---

### 2. Cloud Server Setup

**A. Install Tailscale:**
```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
# Authenticate via the URL provided
```

**B. Install proxy dependencies:**
```bash
pip install httpx
```

**C. Run the reverse proxy:**
```bash
# Replace 100.64.1.2 with your phone's Tailscale IP
python proxy_server.py --backend http://100.64.1.2:8080 --port 8080
```

---

## Testing

From cloud server:
```bash
curl http://100.64.1.2:8081/kaithhealthcheck
# Should return: {"status":"ok"}
```

From internet:
```bash
curl https://your-cloud-domain.com/kaithhealthcheck
```

---

## Production Deployment

### Option 1: systemd service (recommended)

Create `/etc/systemd/system/cantio-proxy.service`:
```ini
[Unit]
Description=Cantio Reverse Proxy to Phone Backend
After=network.target tailscaled.service

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/backend
Environment="PATH=/usr/bin:/usr/local/bin"
ExecStart=/usr/bin/python3 proxy_server.py --backend http://100.64.1.2:8081 --port 8080
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable cantio-proxy
sudo systemctl start cantio-proxy
```

### Option 2: Docker (if needed)

Update your cloud Dockerfile to run the proxy instead of main backend.

---

## Troubleshooting

**Phone backend not reachable:**
```bash
# From cloud server, check Tailscale status
tailscale status

# Ping phone
ping 100.64.1.2

# Test direct connection
curl http://100.64.1.2:8081/kaithhealthcheck
```

**Phone goes to sleep:**
- In Termux: Install `termux-wake-lock` to prevent sleep
- Or use a persistent service manager like `termux-services`

**Keep Termux running in background:**
```bash
# In Termux
pkg install termux-services
sv-enable sshd  # Or create a custom service
```
