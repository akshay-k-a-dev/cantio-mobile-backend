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

# Music-focused platforms - only pure music sources allowed
MUSIC_PLATFORMS = {
    # Primary music platforms
    "youtube", "youtubemusic", "soundcloud", "bandcamp", "spotify", 
    "audiomack", "mixcloud", "applemusic", "deezer", "tidal",
    
    # Direct audio sources
    "generic",  # For direct .mp3, .m3u8 links
}

def is_music_platform(url: str, extractor_key: str = None) -> bool:
    """Check if URL is from a pure music platform (no social media)"""
    url_lower = url.lower()
    
    # Check URL patterns - ONLY pure music platforms
    music_domains = [
        "youtube.com", "youtu.be", "music.youtube.com",
        "soundcloud.com", "bandcamp.com", "spotify.com",
        "audiomack.com", "mixcloud.com", "music.apple.com",
        "deezer.com", "tidal.com",
    ]
    
    if any(domain in url_lower for domain in music_domains):
        return True
    
    # Check extractor key if available
    if extractor_key:
        extractor_lower = extractor_key.lower()
        if any(platform in extractor_lower for platform in MUSIC_PLATFORMS):
            return True
    
    # Allow direct audio file URLs
    if any(url_lower.endswith(ext) for ext in [".mp3", ".m4a", ".opus", ".flac", ".wav", ".aac", ".ogg"]):
        return True
    
    # Allow HLS/DASH audio streams
    if ".m3u8" in url_lower or "stream" in url_lower:
        return True
    
    return False


@app.get("/kaithhealthcheck")
@app.get("/kaithheathcheck")
def health_check():
    return {"status": "ok"}


@app.get("/stream")
def stream(url: str = Query(..., description="Music/audio URL from supported platforms")):
    # Pre-check if URL is from a music platform
    if not is_music_platform(url):
        logger.warning(f"Rejected non-music platform: {url}")
        raise HTTPException(
            status_code=400,
            detail="URL must be from a music platform (YouTube, SoundCloud, Spotify, Bandcamp, TikTok, etc.)"
        )
    
    # Retry logic for bot detection
    MAX_RETRIES = 3
    last_error = None
    
    for attempt in range(MAX_RETRIES):
        try:
            # Base options for all platforms - FORCE AUDIO ONLY
            ydl_opts = {
                "format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best",
                "quiet": True,
                "no_warnings": True,
                "extract_flat": False,
                "skip_download": True,
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "best",
                }],
                "http_headers": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            }
            
            # YouTube-specific optimizations
            if "youtube.com" in url or "youtu.be" in url or "music.youtube.com" in url:
                ydl_opts["extractor_args"] = {
                    "youtube": {
                        "player_client": ["android_music", "android"],
                        "skip": ["webpage", "hls", "dash"],
                    },
                }
                ydl_opts["http_headers"]["User-Agent"] = "com.google.android.youtube/19.09.37 (Linux; U; Android 13) gzip"
                logger.info(f"Using YouTube-specific optimizations (attempt {attempt + 1})")
            
            with YoutubeDL(ydl_opts) as ydl:
                logger.info(f"Extracting from: {url} (attempt {attempt + 1}/{MAX_RETRIES})")
                info = ydl.extract_info(url, download=False)
            
            if not info:
                raise HTTPException(status_code=404, detail="No info extracted")
            
            # Extract platform info first
            extractor = info.get("extractor", "Unknown")
            extractor_key = info.get("extractor_key", "Unknown")
            
            # Double-check extracted content is from music platform
            if not is_music_platform(url, extractor_key):
                logger.warning(f"Extracted from non-music platform: {extractor_key}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Platform '{extractor_key}' is not supported for music streaming"
                )

            stream_url = info.get("url")

            if not stream_url:
                formats = info.get("formats", [])
                # STRICT audio-only filtering - NO VIDEO
                audio_formats = [
                    f for f in formats 
                    if f.get("acodec") != "none" 
                    and (f.get("vcodec") == "none" or f.get("vcodec") is None)
                ]
                
                # If no pure audio, try formats with audio codec
                if not audio_formats:
                    audio_formats = [f for f in formats if f.get("acodec") != "none"]
                    logger.warning("No pure audio formats found, falling back to formats with audio")
                
                if audio_formats:
                    best = max(audio_formats, key=lambda f: f.get("abr") or f.get("tbr") or 0)
                    stream_url = best.get("url")
                    logger.info(f"Selected format: {best.get('format_id')} - codec: {best.get('acodec')}, vcodec: {best.get('vcodec')}")

            if not stream_url:
                raise HTTPException(status_code=404, detail="No audio stream found")
            
            logger.info(f"✓ Successfully extracted from {extractor_key}: {info.get('title', 'Unknown')}")
            
            return {
                "title": info.get("title", "Unknown"),
                "stream_url": stream_url,
                "platform": extractor_key,
                "duration": info.get("duration"),
                "thumbnail": info.get("thumbnail"),
                "uploader": info.get("uploader"),
            }
            
        except HTTPException:
            # Re-raise HTTP exceptions immediately
            raise
        except Exception as e:
            last_error = str(e)
            logger.warning(f"✗ Attempt {attempt + 1}/{MAX_RETRIES} failed: {last_error}")
            
            # If bot detection on YouTube, suggest alternatives
            if "Sign in to confirm" in last_error or "bot" in last_error.lower():
                if "youtube.com" in url or "youtu.be" in url:
                    logger.error(f"YouTube blocked after {attempt + 1} attempts: {url}")
                    raise HTTPException(
                        status_code=403,
                        detail={
                            "error": "YouTube blocked request from datacenter IP",
                            "suggestion": "Try alternative platforms: SoundCloud, Bandcamp, Spotify, or use phone server for YouTube",
                            "alternatives": [
                                "https://soundcloud.com",
                                "https://bandcamp.com",
                                "https://music.apple.com",
                                "https://audiomack.com"
                            ]
                        }
                    )
                
                # For non-YouTube platforms, retry with backoff
                if attempt < MAX_RETRIES - 1:
                    import time
                    backoff = (attempt + 1) * 2
                    logger.info(f"Bot detected, retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
            
            # If this was the last attempt, raise the error
            if attempt == MAX_RETRIES - 1:
                logger.error(f"All {MAX_RETRIES} attempts failed for {url}")
                if "Sign in to confirm" in last_error or "bot" in last_error.lower():
                    raise HTTPException(
                        status_code=403,
                        detail="Platform blocked request. Try alternative music platforms or use phone server.",
                    )
                if "Unsupported URL" in last_error:
                    raise HTTPException(
                        status_code=400,
                        detail="URL not supported by yt-dlp",
                    )
                raise HTTPException(status_code=500, detail=last_error)
