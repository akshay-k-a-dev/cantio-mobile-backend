import logging
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from yt_dlp import YoutubeDL
import re

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

# Alternative platforms to search (in order of preference)
ALTERNATIVE_PLATFORMS = [
    ("soundcloud", "https://soundcloud.com/search?q="),
    ("audiomack", "https://audiomack.com/search?q="),
    ("bandcamp", "https://bandcamp.com/search?q="),
]

def extract_metadata_from_youtube(url: str):
    """Extract song metadata from YouTube URL without downloading"""
    try:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "skip_download": True,
        }
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get("title", "")
            uploader = info.get("uploader", "")
            
            # Clean up title to extract song/artist
            # Remove common patterns like "Official Video", "[Official]", etc.
            clean_title = re.sub(r'\[.*?\]|\(.*?\)|official|video|audio|lyrics|hd|4k', '', title, flags=re.IGNORECASE)
            clean_title = clean_title.strip()
            
            logger.info(f"Extracted metadata - Title: {clean_title}, Uploader: {uploader}")
            return {
                "title": clean_title,
                "artist": uploader,
                "original_title": title,
                "search_query": f"{clean_title} {uploader}".strip()
            }
    except Exception as e:
        logger.error(f"Failed to extract YouTube metadata: {e}")
        return None

def search_alternative_platform(metadata: dict, platform_name: str, search_base: str):
    """Search for song on alternative platform"""
    try:
        search_query = metadata["search_query"]
        search_url = f"{search_base}{search_query.replace(' ', '+')}"
        
        logger.info(f"Searching on {platform_name}: {search_url}")
        
        ydl_opts = {
            "format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "extract_flat": "in_playlist",
            "playlist_items": "1",  # Only get first result
            "skip_download": True,
        }
        
        with YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(f"ytsearch1:{search_query} {platform_name}", download=False)
            
            if result and result.get("entries"):
                entry = result["entries"][0]
                logger.info(f"Found on {platform_name}: {entry.get('title')}")
                return entry.get("url") or entry.get("webpage_url")
    except Exception as e:
        logger.warning(f"Search failed on {platform_name}: {e}")
    
    return None

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
def try_extract_stream(url: str, is_youtube: bool = False, platform_name: str = None, max_retries: int = 2):
    """Try to extract stream from URL with retry logic"""
    last_error = None
    
    for attempt in range(max_retries):
        try:
            # Base options for all platforms - FORCE AUDIO ONLY
            ydl_opts = {
                "format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best",
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
            if is_youtube:
                ydl_opts["extractor_args"] = {
                    "youtube": {
                        "player_client": ["android_music", "android"],
                        "skip": ["webpage", "hls", "dash"],
                    },
                }
                ydl_opts["http_headers"]["User-Agent"] = "com.google.android.youtube/19.09.37 (Linux; U; Android 13) gzip"
                logger.info(f"Using YouTube-specific optimizations (attempt {attempt + 1})")
            
            with YoutubeDL(ydl_opts) as ydl:
                logger.info(f"Extracting from: {url} (attempt {attempt + 1}/{max_retries})")
                info = ydl.extract_info(url, download=False)
            
            if not info:
                return None
            
            # Handle search results
            if "entries" in info:
                if not info["entries"]:
                    return None
                info = info["entries"][0]
            
            # Extract platform info
            extractor = info.get("extractor", "Unknown")
            extractor_key = info.get("extractor_key", "Unknown")
            
            # Double-check extracted content is from music platform
            if not is_music_platform(url, extractor_key):
                logger.warning(f"Extracted from non-music platform: {extractor_key}")
                return None

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
                return None
            
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
            last_error = str(e)
            logger.warning(f"✗ Attempt {attempt + 1}/{max_retries} failed: {last_error}")
            
            # If YouTube bot detection, return None to trigger alternatives
            if is_youtube and ("Sign in to confirm" in last_error or "bot" in last_error.lower()):
                logger.warning("YouTube bot detection - will try alternatives")
                return None
            
            # For non-YouTube, retry with backoff
            if attempt < max_retries - 1:
                import time
                time.sleep(1)
                continue
    
    return None

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
                        status_code=503,
                        detail="YouTube doesn't work from cloud servers. Use SoundCloud, Bandcamp, Spotify, Apple Music, or Audiomack instead. For YouTube, use the phone server proxy."
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
