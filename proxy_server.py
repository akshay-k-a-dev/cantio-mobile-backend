#!/usr/bin/env python3
"""
Reverse proxy for cloud server to forward requests to phone backend via Tailscale.
Automatically checks Tailscale connectivity and ensures connection to phone.
"""
import os
import subprocess
import sys
import time
import httpx
from fastapi import FastAPI, Request, Response
import uvicorn

app = FastAPI()

PHONE_IP = os.getenv("PHONE_IP", "100.87.250.20")
PHONE_PORT = int(os.getenv("PHONE_PORT", "8081"))
BACKEND_URL = f"http://{PHONE_IP}:{PHONE_PORT}"
SKIP_CHECKS = os.getenv("SKIP_CHECKS", "false").lower() == "true"  # For cloud deployments


def run_command(cmd):
    """Run a shell command and return output."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=30
        )
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return 1, "", str(e)


def check_tailscale():
    """Check if Tailscale is installed and running."""
    print("🔍 Checking Tailscale status...")
    
    # Check if tailscale is installed
    code, _, _ = run_command("which tailscale")
    if code != 0:
        print("❌ Tailscale not installed. Installing...")
        code, stdout, stderr = run_command(
            "curl -fsSL https://tailscale.com/install.sh | sh"
        )
        if code != 0:
            print(f"❌ Failed to install Tailscale: {stderr}")
            sys.exit(1)
        print("✅ Tailscale installed")
    
    # Check if tailscale is running
    code, stdout, _ = run_command("tailscale status")
    if code != 0 or "Logged out" in stdout:
        print("⚠️  Tailscale not connected. Attempting to connect...")
        
        # Try to bring up tailscale (without sudo for Docker)
        code, stdout, stderr = run_command("tailscale up")
        
        if code != 0:
            print(f"❌ Failed to connect Tailscale: {stderr}")
            print("\n📋 Manual steps:")
            print("   1. Run: tailscale up")
            print("   2. Open the authentication URL in your browser")
            print("   3. Authenticate and restart this script")
            sys.exit(1)
        
        # Check if authentication URL is in output
        if "https://" in stdout:
            print("\n🔐 Tailscale requires authentication!")
            print("=" * 60)
            print(stdout)
            print("=" * 60)
            print("\n📋 Please:")
            print("   1. Open the URL above in your browser")
            print("   2. Authenticate")
            print("   3. Restart this script")
            sys.exit(0)
        
        # Wait a moment for connection to establish
        time.sleep(2)
        
        # Verify connection
        code, stdout, _ = run_command("tailscale status")
        if code != 0 or "Logged out" in stdout:
            print("❌ Tailscale connection failed. Please run manually:")
            print("   tailscale up")
            sys.exit(1)
    
    print("✅ Tailscale is running")
    return True


def check_phone_connection():
    """Check if phone backend is reachable."""
    print(f"🔍 Checking connection to phone at {BACKEND_URL}...")
    
    # Ping the phone IP
    code, _, _ = run_command(f"ping -c 1 -W 2 {PHONE_IP}")
    if code != 0:
        print(f"❌ Cannot ping {PHONE_IP}")
        print("   Make sure:")
        print("   1. Phone is connected to Tailscale")
        print("   2. Phone backend is running")
        print(f"   3. Tailscale IP {PHONE_IP} is correct")
        sys.exit(1)
    
    print(f"✅ Phone {PHONE_IP} is reachable")
    
    # Check if backend is running
    try:
        response = httpx.get(f"{BACKEND_URL}/kaithhealthcheck", timeout=5.0)
        if response.status_code == 200:
            print(f"✅ Phone backend is responding at {BACKEND_URL}")
            return True
        else:
            print(f"⚠️  Phone backend returned status {response.status_code}")
    except Exception as e:
        print(f"❌ Phone backend not responding: {e}")
        print(f"   Make sure backend is running on phone at port {PHONE_PORT}")
        sys.exit(1)
    
    return False


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def proxy(path: str, request: Request):
    """Forward all requests to the phone backend."""
    url = f"{BACKEND_URL}/{path}"
    
    # Forward query parameters
    if request.url.query:
        url += f"?{request.url.query}"
    
    headers = dict(request.headers)
    headers.pop("host", None)  # Remove host header
    
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            # Forward the request
            response = await client.request(
                method=request.method,
                url=url,
                headers=headers,
                content=await request.body(),
            )
            
            # Return the response
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=dict(response.headers),
            )
    except Exception as e:
        print(f"❌ Error proxying request: {e}")
        return Response(
            content=f"Proxy error: {str(e)}",
            status_code=502,
        )


if __name__ == "__main__":
    print("=" * 60)
    print("🚀 Cantio Reverse Proxy Starting")
    print("=" * 60)
    
    if not SKIP_CHECKS:
        # Check Tailscale
        check_tailscale()
        
        # Check phone connection
        check_phone_connection()
        
        print("=" * 60)
        print(f"✅ All checks passed!")
    else:
        print("⚠️  Running in SKIP_CHECKS mode (cloud deployment)")
        print(f"   Assuming {BACKEND_URL} is reachable")
    
    print(f"🔄 Proxying 0.0.0.0:8080 → {BACKEND_URL}")
    print("=" * 60)
    
    uvicorn.run(app, host="0.0.0.0", port=8080)
