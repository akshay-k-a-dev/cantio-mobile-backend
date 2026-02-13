import logging
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from yt_dlp import YoutubeDL

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


@app.get("/kaithhealthcheck")
@app.get("/kaithheathcheck")
def health_check():
    return {"status": "ok"}


@app.get("/stream")
def stream(url: str = Query(..., description="Any video/audio URL supported by yt-dlp")):
    try:
        # Base options for all platforms
        ydl_opts = {
            "format": "bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "skip_download": True,
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            },
        }
        
        # YouTube-specific optimizations
        if "youtube.com" in url or "youtu.be" in url or "music.youtube.com" in url:
            ydl_opts["extractor_args"] = {
                "youtube": {
                    "player_client": ["android", "android_music", "android_creator"],
                    "skip": ["webpage"],
                },
            }
            ydl_opts["http_headers"]["User-Agent"] = "com.google.android.youtube/19.09.37 (Linux; U; Android 13) gzip"
            logger.info("Using YouTube-specific optimizations")
        
        with YoutubeDL(ydl_opts) as ydl:
            logger.info(f"Extracting from: {url}")
            info = ydl.extract_info(url, download=False)
        
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

        # Extract platform info
        extractor = info.get("extractor", "Unknown")
        extractor_key = info.get("extractor_key", "Unknown")
        
        logger.info(f"✓ Successfully extracted from {extractor_key}: {info.get('title', 'Unknown')}")
        
        return {
            "title": info.get("title", "Unknown"),
            "stream_url": stream_url,
            "platform": extractor_key,
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
            "uploader": info.get("uploader"),
        }
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"yt-dlp extraction failed for {url}: {error_msg}")
        if "Sign in to confirm" in error_msg or "bot" in error_msg.lower():
            raise HTTPException(
                status_code=403,
                detail="Platform blocked request. Try again later.",
            )
        if "Unsupported URL" in error_msg:
            raise HTTPException(
                status_code=400,
                detail="URL not supported by yt-dlp",
            )
        raise HTTPException(status_code=500, detail=error_msg)
