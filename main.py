import logging
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from yt_dlp import YoutubeDL
from fp.fp import FreeProxy
import random

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Enable CORS for all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Proxy pool management
proxy_pool = []
proxy_fetch_attempts = 0
MAX_PROXY_FETCH_ATTEMPTS = 3

def get_fresh_proxy():
    """Fetch a fresh working proxy from free-proxy"""
    global proxy_fetch_attempts
    try:
        proxy_fetch_attempts += 1
        logger.info(f"Fetching fresh proxy (attempt {proxy_fetch_attempts})...")
        proxy = FreeProxy(timeout=2, https=True, rand=True).get()
        logger.info(f"Got proxy: {proxy}")
        return proxy
    except Exception as e:
        logger.warning(f"Failed to fetch proxy: {e}")
        return None

def get_proxy_for_request():
    """Get a proxy from pool or fetch a fresh one"""
    global proxy_pool
    
    # Try to use existing proxy from pool
    if proxy_pool and random.random() < 0.7:  # 70% chance to reuse
        proxy = random.choice(proxy_pool)
        logger.info(f"Reusing proxy from pool: {proxy}")
        return proxy
    
    # Fetch new proxy
    proxy = get_fresh_proxy()
    if proxy:
        # Add to pool (keep max 5 proxies)
        if proxy not in proxy_pool:
            proxy_pool.append(proxy)
            if len(proxy_pool) > 5:
                proxy_pool.pop(0)
    
    return proxy


@app.get("/kaithhealthcheck")
@app.get("/kaithheathcheck")
def health_check():
    return {
        "status": "ok",
        "proxy_pool_size": len(proxy_pool),
        "proxies": proxy_pool[:3]  # Show first 3 for debugging
    }


@app.get("/stream")
def stream(url: str = Query(..., description="YouTube video URL")):
    MAX_RETRIES = 3
    last_error = None
    
    for attempt in range(MAX_RETRIES):
        try:
            # Get proxy for this attempt
            proxy = get_proxy_for_request()
            
            # Build YDL options with proxy
            ydl_opts = {
                "format": "bestaudio/best",
                "quiet": True,
                "no_warnings": True,
                "extract_flat": False,
                "skip_download": True,
                "extractor_args": {
                    "youtube": {
                        "player_client": ["android", "android_music", "android_creator"],
                        "skip": ["webpage"],
                    },
                },
                "http_headers": {
                    "User-Agent": "com.google.android.youtube/19.09.37 (Linux; U; Android 13) gzip",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            }
            
            if proxy:
                ydl_opts["proxy"] = proxy
                logger.info(f"Attempt {attempt + 1}/{MAX_RETRIES} using proxy: {proxy}")
            else:
                logger.warning(f"Attempt {attempt + 1}/{MAX_RETRIES} - no proxy available, trying direct")
            
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            
            # Success! Extract stream URL
            if not info:
                raise HTTPException(status_code=404, detail="No info extracted")

            stream_url = info.get("url")

            if not stream_url:
                formats = info.get("formats", [])
                audio_formats = [f for f in formats if f.get("acodec") != "none" and f.get("vcodec") in (None, "none")]
                if not audio_formats:
                    audio_formats = [f for f in formats if f.get("acodec") != "none"]
                if audio_formats:
                    best = max(audio_formats, key=lambda f: f.get("abr") or f.get("tbr") or 0)
                    stream_url = best.get("url")

            if not stream_url:
                raise HTTPException(status_code=404, detail="No audio stream found")

            logger.info(f"✓ Successfully extracted stream on attempt {attempt + 1}")
            return {
                "title": info.get("title", "Unknown"),
                "stream_url": stream_url,
            }
            
        except Exception as e:
            last_error = str(e)
            logger.warning(f"✗ Attempt {attempt + 1}/{MAX_RETRIES} failed: {last_error}")
            
            # Remove failed proxy from pool
            if proxy and proxy in proxy_pool:
                proxy_pool.remove(proxy)
                logger.info(f"Removed failed proxy from pool")
            
            # If this was the last attempt, raise the error
            if attempt == MAX_RETRIES - 1:
                logger.error(f"All {MAX_RETRIES} attempts failed for {url}")
                if "Sign in to confirm" in last_error or "bot" in last_error.lower():
                    raise HTTPException(
                        status_code=403,
                        detail="YouTube blocked all proxy attempts. Try again later.",
                    )
                raise HTTPException(status_code=500, detail=f"Failed after {MAX_RETRIES} attempts: {last_error}")
            
            # Wait a bit before retry
            import time
            time.sleep(0.5)
    
    # Should never reach here
    raise HTTPException(status_code=500, detail="Unexpected error")
