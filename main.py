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
    # Pre-check if URL is from a music platform
    if not is_music_platform(url):
        logger.warning(f"Rejected non-music platform: {url}")
        raise HTTPException(
            status_code=400,
            detail="URL must be from a music platform (YouTube, SoundCloud, Spotify, Bandcamp, etc.)"
        )
    
    is_youtube = "youtube.com" in url or "youtu.be" in url or "music.youtube.com" in url
    
    # Try YouTube first (if it's a YouTube URL)
    if is_youtube:
        result = try_extract_stream(url, is_youtube=True)
        
        # If YouTube blocked, try alternatives
        if result is None:
            logger.warning("YouTube blocked, attempting alternative platforms...")
            metadata = extract_metadata_from_youtube(url)
            
            if metadata:
                logger.info(f"Searching alternatives for: {metadata['search_query']}")
                
                # Try each alternative platform
                for platform_name, search_base in ALTERNATIVE_PLATFORMS:
                    logger.info(f"Trying {platform_name}...")
                    
                    # Search and get the URL from alternative platform
                    search_query = metadata["search_query"]
                    alternative_url = None
                    
                    try:
                        # Use yt-dlp's search to find song on platform
                        if platform_name == "soundcloud":
                            alternative_url = f"scsearch1:{search_query}"
                        elif platform_name == "audiomack":
                            # Direct search on audiomack
                            alternative_url = f"https://audiomack.com/search?q={search_query.replace(' ', '+')}"
                        elif platform_name == "bandcamp":
                            # Bandcamp search
                            alternative_url = f"https://bandcamp.com/search?q={search_query.replace(' ', '+')}"
                        
                        if alternative_url:
                            result = try_extract_stream(alternative_url, is_youtube=False, platform_name=platform_name)
                            
                            if result:
                                result["fallback_from_youtube"] = True
                                result["original_query"] = metadata["original_title"]
                                logger.info(f"✓ Found alternative on {platform_name}")
                                return result
                    except Exception as e:
                        logger.warning(f"Failed to search {platform_name}: {e}")
                        continue
                
                # If all alternatives failed
                raise HTTPException(
                    status_code=503,
                    detail=f"YouTube blocked and couldn't find '{metadata['original_title']}' on alternative platforms. Try SoundCloud/Bandcamp directly."
                )
            else:
                raise HTTPException(
                    status_code=503,
                    detail="YouTube blocked and couldn't extract metadata for alternative search."
                )
        
        return result
    else:
        # Non-YouTube URL - try directly
        result = try_extract_stream(url, is_youtube=False)
        if result is None:
            raise HTTPException(status_code=500, detail="Failed to extract stream")
        return result


def try_extract_stream(url: str, is_youtube: bool = False, platform_name: str = None, max_retries: int = 2):
    """Try to extract stream from URL with retry logic"""
    last_error = None
    
    for attempt in range(max_retries):
        try:
            # Base options for all platforms - FORCE AUDIO ONLY
            ydl_opts = {
                # Force best audio-only formats (no video)
                "format": "bestaudio[vcodec=none]/bestaudio[acodec=opus]/bestaudio[acodec=vorbis]/bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio",
                "quiet": True,
                "no_warnings": True,
                "extract_flat": False,
                "skip_download": True,
                "prefer_free_formats": True,
                "postprocessors": [],  # No post-processing for streaming
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
                
                # ULTRA STRICT audio-only filtering - ABSOLUTELY NO VIDEO
                audio_only_formats = []
                
                for f in formats:
                    vcodec = f.get("vcodec", "")
                    acodec = f.get("acodec", "")
                    
                    # Must have audio codec
                    if acodec == "none" or not acodec:
                        continue
                    
                    # Must NOT have video codec
                    if vcodec and vcodec != "none":
                        continue
                    
                    # Prefer specific audio formats
                    ext = f.get("ext", "")
                    if ext in ["m4a", "mp3", "opus", "ogg", "webm", "wav", "aac", "flac"]:
                        audio_only_formats.append(f)
                
                if not audio_only_formats:
                    # Fallback: any format with audio and no video
                    audio_only_formats = [
                        f for f in formats 
                        if f.get("acodec") not in ["none", None, ""] 
                        and f.get("vcodec") in ["none", None, ""]
                    ]
                
                if not audio_only_formats:
                    logger.error(f"No pure audio formats found. Available formats: {[f.get('format_id') for f in formats]}")
                    return None
                
                # Select best audio format by bitrate
                best = max(audio_only_formats, key=lambda f: f.get("abr") or f.get("tbr") or 0)
                stream_url = best.get("url")
                
                format_info = {
                    "format_id": best.get("format_id"),
                    "ext": best.get("ext"),
                    "acodec": best.get("acodec"),
                    "vcodec": best.get("vcodec"),
                    "abr": best.get("abr"),
                }
                logger.info(f"✓ Selected audio-only format: {format_info}")

            if not stream_url:
                return None
            
            logger.info(f"✓ Successfully extracted from {extractor_key}: {info.get('title', 'Unknown')}")
            
            # Get format extension for audio type
            format_ext = info.get("ext", "unknown")
            if "formats" in locals() and audio_only_formats:
                format_ext = best.get("ext", format_ext)
            
            return {
                "title": info.get("title", "Unknown"),
                "stream_url": stream_url,
                "platform": extractor_key,
                "duration": info.get("duration"),
                "thumbnail": info.get("thumbnail"),
                "uploader": info.get("uploader"),
                "audio_format": format_ext,
                "is_audio_only": True,
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
