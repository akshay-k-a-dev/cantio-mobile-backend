import logging
import os
import random
from pathlib import Path
from functools import lru_cache
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from yt_dlp import YoutubeDL
import re
import httpx
import time

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

# Legacy search API
LEGACY_API_BASE = "https://music-mu-lovat.vercel.app"

# Music-focused platforms - only pure music sources allowed
MUSIC_PLATFORMS = {
    # Primary music platforms
    "youtube", "youtubemusic", "soundcloud", "bandcamp", "spotify", 
    "audiomack", "mixcloud", "applemusic", "deezer", "tidal",
    
    # Direct audio sources
    "generic",  # For direct .mp3, .m3u8 links
}

# URL patterns for music platforms
MUSIC_URL_PATTERNS = [
    "youtube.com", "youtu.be", "music.youtube.com",
    "soundcloud.com", "bandcamp.com", "spotify.com",
    "audiomack.com", "mixcloud.com", "apple.com/music",
    "deezer.com", "tidal.com",
]

# Alternative platforms to search (in order of preference)
ALTERNATIVE_PLATFORMS = [
    ("soundcloud", "scsearch1:"),
    ("audiomack", "https://audiomack.com/search?q="),
    ("bandcamp", "https://bandcamp.com/search?q="),
]

# User agents for randomization - reduces pattern detection
USER_AGENTS = [
    "com.google.android.youtube/19.09.37 (Linux; U; Android 13) gzip",
    "com.google.android.youtube/19.02.39 (Linux; U; Android 12) gzip",
    "com.google.android.youtube/18.45.41 (Linux; U; Android 11) gzip",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

# YouTube client configurations - each bypasses different restrictions
# android_vr is currently the most reliable (as of March 2026)
YOUTUBE_CLIENTS = [
    {
        "name": "android_vr",
        "player_client": ["android_vr"],
        "user_agent": "com.google.android.apps.youtube.vr.oculus/1.57.29 (Linux; U; Android 12; Quest 2 Build/SQ3A.220605.009.A1) gzip",
    },
    {
        "name": "android_music",
        "player_client": ["android_music"],
        "user_agent": "com.google.android.apps.youtube.music/6.42.52 (Linux; U; Android 13) gzip",
    },
    {
        "name": "android",
        "player_client": ["android"],
        "user_agent": "com.google.android.youtube/19.09.37 (Linux; U; Android 13) gzip",
    },
    {
        "name": "web",
        "player_client": ["web"],
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    },
]

# Simple in-memory cache for stream URLs (survives within same container)
_stream_cache = {}
_cache_ttl = 300  # 5 minutes


def get_cached_stream(url: str) -> dict | None:
    """Get cached stream data if not expired"""
    if url in _stream_cache:
        data, timestamp = _stream_cache[url]
        if time.time() - timestamp < _cache_ttl:
            logger.info(f"Cache HIT for: {url[:50]}...")
            return data
        else:
            del _stream_cache[url]
    return None


def set_cached_stream(url: str, data: dict):
    """Cache stream data with TTL"""
    _stream_cache[url] = (data, time.time())
    # Basic cache cleanup - remove oldest entries if cache gets too big
    if len(_stream_cache) > 100:
        oldest_key = min(_stream_cache.keys(), key=lambda k: _stream_cache[k][1])
        del _stream_cache[oldest_key]


def is_music_platform(url: str, extractor_key: str = None) -> bool:
    """Check if URL is from a pure music platform (no social media)"""
    url_lower = url.lower()
    
    # Check URL patterns first
    for pattern in MUSIC_URL_PATTERNS:
        if pattern in url_lower:
            return True
    
    # Allow direct audio file URLs
    if any(ext in url_lower for ext in [".mp3", ".m4a", ".wav", ".flac", ".ogg", ".opus", ".aac"]):
        return True
    
    # Allow HLS/DASH audio streams
    if ".m3u8" in url_lower or "stream" in url_lower:
        return True
    
    # Check extractor key if provided
    if extractor_key:
        extractor_lower = extractor_key.lower()
        return any(platform in extractor_lower for platform in MUSIC_PLATFORMS)
    
    # Allow search queries (scsearch, ytsearch, etc.)
    if url_lower.startswith(("scsearch", "ytsearch", "bcsearch")):
        return True
    
    return False


async def search_legacy_api(query: str):
    """Search the legacy Cantio API for track information"""
    try:
        logger.info(f"Searching legacy API for: {query}")
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{LEGACY_API_BASE}/api/search",
                params={"q": query}
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Check if we have results
                if data and isinstance(data, list) and len(data) > 0:
                    # Get first result - API returns: {videoId, title, artist, duration, thumbnail}
                    track = data[0]
                    video_id = track.get("videoId")
                    title = track.get("title", "Unknown")
                    artist = track.get("artist", "Unknown")
                    duration = track.get("duration", 0)
                    thumbnail = track.get("thumbnail", "")
                    
                    if video_id:
                        logger.info(f"✓ Legacy API found: {title} by {artist} (ID: {video_id})")
                        return {
                            "video_id": video_id,
                            "title": title,
                            "artist": artist,
                            "duration": duration,
                            "thumbnail": thumbnail,
                            "youtube_url": f"https://www.youtube.com/watch?v={video_id}"
                        }
                
                logger.warning("Legacy API returned no results")
                return None
                
    except Exception as e:
        logger.error(f"Legacy API search failed: {e}")
        return None


def extract_metadata_from_youtube(url: str):
    """Extract song metadata from YouTube URL using yt-dlp (lightweight extraction)"""
    try:
        logger.info(f"Extracting metadata for: {url}")
        
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,  # Lightweight - no format extraction
            "skip_download": True,
        }
        
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get("title", "")
            uploader = info.get("uploader", "")
            
            # Clean up title to extract song/artist
            clean_title = re.sub(
                r'\[.*?\]|\(.*?\)|official|video|audio|lyrics|hd|4k|music video|mv|ft\.|feat\.',
                '', 
                title, 
                flags=re.IGNORECASE
            )
            clean_title = clean_title.strip()
            
            # Try to parse artist - song format
            if " - " in clean_title:
                parts = clean_title.split(" - ", 1)
                artist = parts[0].strip()
                song = parts[1].strip()
            else:
                artist = uploader
                song = clean_title
            
            search_query = f"{song} {artist}".strip()
            
            logger.info(f"✓ Metadata extracted - Song: {song}, Artist: {artist}")
            
            return {
                "title": song,
                "artist": artist,
                "original_title": title,
                "search_query": search_query,
                "duration": info.get("duration"),
                "thumbnail": info.get("thumbnail"),
            }
    except Exception as e:
        logger.error(f"Metadata extraction failed: {e}")
        return None


def extract_best_audio_format(formats: list) -> dict | None:
    """
    Extract best audio format from format list.
    RELAXED filtering - prioritize getting ANY audio over being strict.
    """
    if not formats:
        return None
    
    # Strategy 1: Formats with audio codec (don't be strict about video)
    audio_formats = [
        f for f in formats 
        if f.get("acodec") not in [None, "none", ""]
    ]
    
    # Strategy 2: If no explicit audio codec, try formats marked as audio
    if not audio_formats:
        audio_formats = [
            f for f in formats 
            if f.get("format_note", "").lower() in ["audio", "audio only"]
            or f.get("resolution") == "audio only"
        ]
    
    # Strategy 3: Pure audio-only (vcodec=none, acodec present) - strict fallback
    if not audio_formats:
        audio_formats = [
            f for f in formats 
            if f.get("acodec") not in ["none", None, ""] 
            and f.get("vcodec") in ["none", None, ""]
        ]
    
    # Strategy 4: Last resort - any format with a URL
    if not audio_formats:
        audio_formats = [f for f in formats if f.get("url")]
    
    if not audio_formats:
        return None
    
    # Select best by bitrate (audio bitrate or total bitrate)
    best = max(audio_formats, key=lambda f: f.get("abr") or f.get("tbr") or f.get("filesize") or 0)
    return best


def try_extract_with_client(url: str, client_config: dict) -> dict | None:
    """Try extraction with a specific YouTube client configuration"""
    try:
        ydl_opts = {
            "format": "bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "skip_download": True,
            "socket_timeout": 15,  # Fast fail on Vercel
            "extractor_args": {
                "youtube": {
                    "player_client": client_config["player_client"],
                }
            },
            "http_headers": {
                "User-Agent": client_config["user_agent"],
                "Accept-Language": "en-US,en;q=0.9",
            },
        }
        
        logger.info(f"Trying {client_config['name']} client...")
        
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        
        if info:
            return info
            
    except Exception as e:
        error_str = str(e).lower()
        # Detect bot blocking
        if "sign in to confirm" in error_str or "bot" in error_str:
            logger.warning(f"{client_config['name']} client: Bot detection triggered")
        else:
            logger.warning(f"{client_config['name']} client failed: {e}")
    
    return None


def try_extract_stream(url: str, is_youtube: bool = False, platform_name: str = None) -> dict | None:
    """
    Multi-strategy stream extraction optimized for serverless.
    Uses multiple YouTube clients as fallback, relaxed format filtering.
    """
    
    # Check cache first
    cached = get_cached_stream(url)
    if cached:
        return cached
    
    info = None
    
    if is_youtube:
        # Try each YouTube client until one works
        for client_config in YOUTUBE_CLIENTS:
            info = try_extract_with_client(url, client_config)
            if info:
                logger.info(f"✓ {client_config['name']} client succeeded")
                break
        
        if not info:
            logger.warning("All YouTube clients failed")
            return None
    else:
        # Non-YouTube: single attempt with randomized user agent
        try:
            ydl_opts = {
                "format": "bestaudio/best",
                "quiet": True,
                "no_warnings": True,
                "extract_flat": False,
                "skip_download": True,
                "socket_timeout": 15,
                "http_headers": {
                    "User-Agent": random.choice(USER_AGENTS),
                    "Accept-Language": "en-US,en;q=0.9",
                },
            }
            
            with YoutubeDL(ydl_opts) as ydl:
                logger.info(f"Extracting from: {url}")
                info = ydl.extract_info(url, download=False)
                
        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            return None
    
    if not info:
        return None
    
    # Handle search results (entries array)
    if "entries" in info:
        if not info["entries"]:
            return None
        info = info["entries"][0]
    
    # Extract platform info
    extractor_key = info.get("extractor_key", "Unknown")
    
    # Validate music platform
    if not is_music_platform(url, extractor_key):
        logger.warning(f"Extracted from non-music platform: {extractor_key}")
        return None
    
    # Get stream URL
    stream_url = info.get("url")
    format_ext = info.get("ext", "unknown")
    
    if not stream_url:
        formats = info.get("formats", [])
        
        if not formats:
            logger.error("No formats available in extraction result")
            return None
        
        # Use relaxed format extraction
        best = extract_best_audio_format(formats)
        
        if not best:
            logger.error(f"No usable audio format found. Available: {[f.get('format_id') for f in formats[:10]]}")
            return None
        
        stream_url = best.get("url")
        format_ext = best.get("ext", format_ext)
        
        logger.info(f"✓ Selected format: id={best.get('format_id')}, ext={best.get('ext')}, "
                   f"acodec={best.get('acodec')}, abr={best.get('abr')}")
    
    if not stream_url:
        logger.error("No stream URL in extraction result")
        return None
    
    logger.info(f"✓ Successfully extracted from {extractor_key}: {info.get('title', 'Unknown')}")
    
    result = {
        "title": info.get("title", "Unknown"),
        "stream_url": stream_url,
        "platform": extractor_key,
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "uploader": info.get("uploader"),
        "audio_format": format_ext,
        "is_audio_only": True,
    }
    
    # Cache successful extraction
    set_cached_stream(url, result)
    
    return result


@app.get("/kaithhealthcheck")
@app.get("/kaithheathcheck")
def health_check():
    return {"status": "ok"}


@app.get("/stream")
async def stream(url: str = Query(..., description="Music/audio URL from supported platforms")):
    """
    Extract stream URL from music platforms.
    Optimized for serverless with multi-client fallback and caching.
    """
    # Pre-check if URL is from a music platform
    if not is_music_platform(url):
        logger.warning(f"Rejected non-music platform: {url}")
        raise HTTPException(
            status_code=400,
            detail="URL must be from a music platform (YouTube, SoundCloud, Spotify, Bandcamp, etc.)"
        )
    
    is_youtube = "youtube.com" in url or "youtu.be" in url or "music.youtube.com" in url
    
    # Try extraction (with caching and multi-client for YouTube)
    if is_youtube:
        result = try_extract_stream(url, is_youtube=True)
        
        # If YouTube extraction failed, try SoundCloud search as fallback
        if result is None:
            logger.warning("YouTube extraction failed, trying SoundCloud search...")
            
            # Extract metadata for search
            metadata = extract_metadata_from_youtube(url)
            
            if metadata:
                search_query = metadata["search_query"]
                logger.info(f"Searching SoundCloud for: {search_query}")
                
                # Try SoundCloud search (most reliable alternative)
                sc_result = try_extract_stream(f"scsearch1:{search_query}", is_youtube=False, platform_name="soundcloud")
                
                if sc_result:
                    sc_result["fallback_from_youtube"] = True
                    sc_result["original_query"] = metadata["original_title"]
                    logger.info("✓ Found on SoundCloud as fallback")
                    return sc_result
            
            raise HTTPException(
                status_code=503,
                detail="YouTube extraction failed (possible bot detection). Try a direct SoundCloud or Bandcamp link."
            )
        
        return result
    else:
        # Non-YouTube URL - try directly
        result = try_extract_stream(url, is_youtube=False)
        if result is None:
            raise HTTPException(status_code=500, detail="Failed to extract stream")
        return result


@app.get("/cache/stats")
def cache_stats():
    """Debug endpoint to check cache status"""
    return {
        "cached_urls": len(_stream_cache),
        "cache_ttl_seconds": _cache_ttl,
    }


@app.get("/cache/clear")
def cache_clear():
    """Debug endpoint to clear cache"""
    _stream_cache.clear()
    return {"status": "cleared"}


@app.get("/proxy")
async def proxy_stream(
    url: str = Query(..., description="YouTube or music URL to proxy"),
    video_id: str = Query(None, description="YouTube video ID (shortcut, avoids URL parsing)")
):
    """
    Proxy streaming endpoint - extracts audio and streams it directly to the client.
    This bypasses YouTube's IP-binding restriction since the backend fetches and forwards the data.
    
    Optimized for LeapCell (900s timeout, 100MB payload limit).
    Streams in chunks to avoid memory issues with large files.
    """
    # Build URL from video_id if provided
    if video_id:
        url = f"https://www.youtube.com/watch?v={video_id}"
    
    if not is_music_platform(url):
        raise HTTPException(
            status_code=400,
            detail="URL must be from a music platform"
        )
    
    is_youtube = "youtube.com" in url or "youtu.be" in url or "music.youtube.com" in url
    
    # Extract stream URL
    result = try_extract_stream(url, is_youtube=is_youtube)
    
    if not result or not result.get("stream_url"):
        raise HTTPException(
            status_code=503,
            detail="Failed to extract stream URL"
        )
    
    stream_url = result["stream_url"]
    title = result.get("title", "Unknown")
    audio_format = result.get("audio_format", "webm")
    
    # Determine content type
    content_type_map = {
        "webm": "audio/webm",
        "m4a": "audio/mp4",
        "mp3": "audio/mpeg",
        "opus": "audio/opus",
        "ogg": "audio/ogg",
        "aac": "audio/aac",
    }
    content_type = content_type_map.get(audio_format, "audio/webm")
    
    logger.info(f"Proxying stream for: {title} ({content_type})")
    
    async def stream_generator():
        """Stream audio data in chunks"""
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=30.0)) as client:
            try:
                async with client.stream("GET", stream_url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "*/*",
                    "Accept-Encoding": "identity",  # Don't compress, we're streaming
                    "Range": "bytes=0-",  # Request full file
                }) as response:
                    if response.status_code >= 400:
                        logger.error(f"Upstream returned {response.status_code}")
                        return
                    
                    # Stream in 64KB chunks for smooth playback
                    async for chunk in response.aiter_bytes(chunk_size=65536):
                        yield chunk
                        
            except Exception as e:
                logger.error(f"Proxy streaming error: {e}")
                return
    
    # Return streaming response with appropriate headers
    return StreamingResponse(
        stream_generator(),
        media_type=content_type,
        headers={
            "Content-Disposition": f'inline; filename="{title}.{audio_format}"',
            "Accept-Ranges": "bytes",
            "Cache-Control": "no-cache",
            "X-Content-Title": title,
            "X-Content-Platform": result.get("platform", "Unknown"),
            "X-Content-Duration": str(result.get("duration", 0)),
        }
    )


@app.get("/proxy/info")
async def proxy_info(
    url: str = Query(None, description="YouTube or music URL"),
    video_id: str = Query(None, description="YouTube video ID")
):
    """
    Get stream info without proxying - returns metadata and a proxy URL.
    The client can then use the proxy URL for playback.
    """
    if video_id:
        url = f"https://www.youtube.com/watch?v={video_id}"
    
    if not url:
        raise HTTPException(status_code=400, detail="Either url or video_id is required")
    
    if not is_music_platform(url):
        raise HTTPException(status_code=400, detail="URL must be from a music platform")
    
    is_youtube = "youtube.com" in url or "youtu.be" in url or "music.youtube.com" in url
    
    result = try_extract_stream(url, is_youtube=is_youtube)
    
    if not result:
        raise HTTPException(status_code=503, detail="Failed to extract stream info")
    
    # Build proxy URL for the client to use
    if video_id:
        proxy_url = f"/proxy?video_id={video_id}"
    else:
        proxy_url = f"/proxy?url={url}"
    
    return {
        "title": result.get("title"),
        "duration": result.get("duration"),
        "thumbnail": result.get("thumbnail"),
        "uploader": result.get("uploader"),
        "platform": result.get("platform"),
        "audio_format": result.get("audio_format"),
        "proxy_url": proxy_url,
    }
