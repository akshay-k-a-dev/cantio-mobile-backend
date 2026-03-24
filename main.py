"""
Cantio Mobile Backend - SoundCloud Track Resolver

This backend resolves YouTube track metadata to SoundCloud stream URLs.
It uses intelligent matching to find the best SoundCloud match for a given track.

Architecture:
- Primary: SoundCloud resolution via soundcloud-v2 library
- Fallback: Client handles YouTube extraction (residential IP)
- Caching: File-based with 7-day TTL

Author: Cantio Team
Date: March 2026
"""

import logging
from datetime import datetime
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from track_resolver import TrackResolver, ResolverCache

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Cantio Track Resolver",
    description="Resolves YouTube tracks to SoundCloud stream URLs",
    version="2.0.0"
)

# Enable CORS for all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize resolver and cache
cache = ResolverCache()
resolver = TrackResolver(cache=cache)

# Statistics tracking
stats = {
    "total_requests": 0,
    "soundcloud_success": 0,
    "no_match": 0,
    "errors": 0,
    "cache_hits": 0,
    "started_at": datetime.now().isoformat()
}


# Request/Response Models
class ResolveRequest(BaseModel):
    """Request body for track resolution"""
    title: str = Field(..., description="Track title from YouTube")
    artist: str = Field(..., description="Artist name from YouTube")
    duration: int = Field(..., description="Duration in seconds")
    videoId: str = Field(..., description="YouTube video ID (for caching)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "title": "back to friends",
                "artist": "sombr",
                "duration": 202,
                "videoId": "c8zq4kAn_O0"
            }
        }


class ResolveSuccessResponse(BaseModel):
    """Successful resolution response"""
    success: bool = True
    platform: str
    stream_url: str
    title: str
    artist: str
    duration: int
    confidence: float
    soundcloud_id: int
    permalink_url: str
    cached: bool


class ResolveFailureResponse(BaseModel):
    """Failed resolution response"""
    success: bool = False
    reason: str
    confidence: Optional[float] = None
    message: str


# Health check endpoints (keep for compatibility)
@app.get("/kaithhealthcheck")
@app.get("/kaithheathcheck")
def health_check():
    """Health check endpoint"""
    return {
        "status": "ok",
        "service": "cantio-track-resolver",
        "version": "2.0.0",
        "timestamp": datetime.now().isoformat()
    }


@app.post("/api/resolve", response_model=ResolveSuccessResponse | ResolveFailureResponse)
async def resolve_track(request: ResolveRequest):
    """
    Resolve YouTube track to SoundCloud stream URL.
    
    Returns successful resolution with stream URL if confidence >= 0.70,
    otherwise returns failure with reason.
    """
    stats["total_requests"] += 1
    
    try:
        logger.info(
            f"Resolve request: {request.title} by {request.artist} "
            f"({request.duration}s, ID: {request.videoId})"
        )
        
        # Attempt resolution
        resolved = await resolver.resolve(
            youtube_title=request.title,
            youtube_artist=request.artist,
            youtube_duration=request.duration,
            youtube_video_id=request.videoId
        )
        
        if resolved:
            # Success - track resolved with sufficient confidence
            if resolved.cached:
                stats["cache_hits"] += 1
            
            stats["soundcloud_success"] += 1
            
            logger.info(
                f"✓ Resolved {request.videoId} to SoundCloud "
                f"(confidence: {resolved.confidence:.3f}, cached: {resolved.cached})"
            )
            
            return {
                "success": True,
                "platform": resolved.platform,
                "stream_url": resolved.stream_url,
                "title": resolved.title,
                "artist": resolved.artist,
                "duration": resolved.duration,
                "confidence": resolved.confidence,
                "soundcloud_id": resolved.soundcloud_id,
                "permalink_url": resolved.permalink_url,
                "cached": resolved.cached
            }
        else:
            # No match found with sufficient confidence
            stats["no_match"] += 1
            
            logger.warning(f"No confident match for {request.videoId}")
            
            return {
                "success": False,
                "reason": "no_match_found",
                "confidence": None,
                "message": "No SoundCloud track found with sufficient confidence (>= 0.70). "
                          "Client should fallback to YouTube extraction."
            }
            
    except Exception as e:
        stats["errors"] += 1
        
        logger.error(f"Resolution error for {request.videoId}: {e}", exc_info=True)
        
        return {
            "success": False,
            "reason": "error",
            "confidence": None,
            "message": f"Internal error during resolution: {str(e)}"
        }


@app.get("/api/stats")
def get_stats():
    """Get resolver statistics"""
    cache_stats = cache.get_stats()
    
    # Calculate success rate
    total = stats["total_requests"]
    success_rate = (stats["soundcloud_success"] / total * 100) if total > 0 else 0.0
    cache_hit_rate = (stats["cache_hits"] / total * 100) if total > 0 else 0.0
    
    return {
        "resolver_stats": {
            **stats,
            "success_rate_percent": round(success_rate, 2),
            "cache_hit_rate_percent": round(cache_hit_rate, 2),
        },
        "cache_stats": cache_stats
    }


@app.get("/api/cache/stats")
def cache_stats_endpoint():
    """Get cache statistics"""
    return cache.get_stats()


@app.post("/api/cache/cleanup")
def cache_cleanup_endpoint():
    """Remove expired cache entries"""
    removed = cache.cleanup_expired()
    return {
        "status": "cleanup_complete",
        "removed_entries": removed
    }


@app.post("/api/cache/clear")
def cache_clear_endpoint():
    """Clear entire cache (use with caution)"""
    removed = cache.clear_all()
    return {
        "status": "cache_cleared",
        "removed_entries": removed
    }


@app.post("/api/stats/reset")
def reset_stats():
    """Reset statistics (for testing/debugging)"""
    global stats
    old_stats = stats.copy()
    
    stats["total_requests"] = 0
    stats["soundcloud_success"] = 0
    stats["no_match"] = 0
    stats["errors"] = 0
    stats["cache_hits"] = 0
    stats["started_at"] = datetime.now().isoformat()
    
    return {
        "status": "stats_reset",
        "previous_stats": old_stats
    }


# Startup event
@app.on_event("startup")
async def startup_event():
    """Run on application startup"""
    logger.info("=" * 70)
    logger.info("Cantio Track Resolver starting...")
    logger.info("=" * 70)
    logger.info(f"Cache directory: {cache.cache_dir}")
    logger.info(f"Cache TTL: {cache.ttl_days} days")
    logger.info(f"Minimum confidence threshold: {resolver.matcher.MIN_CONFIDENCE}")
    
    # Cleanup expired cache on startup
    removed = cache.cleanup_expired()
    logger.info(f"Startup cache cleanup: {removed} expired entries removed")
    
    cache_stats_data = cache.get_stats()
    logger.info(f"Cache status: {cache_stats_data['valid_entries']} valid entries, "
                f"{cache_stats_data['total_size_mb']} MB")
    
    logger.info("✓ Resolver ready!")
    logger.info("=" * 70)


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown"""
    logger.info("Cantio Track Resolver shutting down...")
    logger.info(f"Final stats: {stats}")
