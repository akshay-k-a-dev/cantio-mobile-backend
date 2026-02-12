from fastapi import FastAPI, HTTPException, Query
from yt_dlp import YoutubeDL

app = FastAPI()

YDL_OPTS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "extract_flat": False,
    "skip_download": True,
}


@app.get("/stream")
def stream(url: str = Query(..., description="YouTube video URL")):
    try:
        with YoutubeDL(YDL_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
