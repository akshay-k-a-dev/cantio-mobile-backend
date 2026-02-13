import logging
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from yt_dlp import YoutubeDL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

COOKIES_FILE = Path(__file__).parent / "cookies.txt"


@app.get("/kaithhealthcheck")
@app.get("/kaithheathcheck")
def health_check():
    return {"status": "ok"}

YDL_OPTS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "extract_flat": False,
    "skip_download": True,
    "extractor_args": {
        "youtube": {
            "player_client": ["android_vr", "web_creator"],
        },
    },
    "http_headers": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.youtube.com/",
    },
}

if COOKIES_FILE.exists():
    YDL_OPTS["cookiefile"] = str(COOKIES_FILE)


@app.get("/stream")
def stream(url: str = Query(..., description="YouTube video URL")):
    try:
        with YoutubeDL(YDL_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        error_msg = str(e)
        logger.error(f"yt-dlp extraction failed for {url}: {error_msg}")
        if "Sign in to confirm" in error_msg or "bot" in error_msg.lower():
            raise HTTPException(
                status_code=403,
                detail="YouTube requires fresh authentication. Cookies may be expired.",
            )
        raise HTTPException(status_code=500, detail=error_msg)

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

    return {
        "title": info.get("title", "Unknown"),
        "stream_url": stream_url,
    }
