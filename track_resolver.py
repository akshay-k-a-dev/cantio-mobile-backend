"""
Track Resolver - SoundCloud to YouTube track matching system.

Resolves YouTube tracks to SoundCloud stream URLs using intelligent matching:
- String normalization and similarity scoring
- Multi-factor scoring (title, artist, duration)
- File-based caching with TTL
- Confidence thresholds to ensure quality matches

Author: Cantio Team
Date: March 2026
"""

import re
import pickle
import unicodedata
from pathlib import Path
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, asdict
import logging

from soundcloud import SoundCloud

logger = logging.getLogger(__name__)


@dataclass
class ResolvedTrack:
    """Represents a successfully resolved track"""
    platform: str  # "soundcloud"
    stream_url: str
    title: str
    artist: str
    duration: int  # seconds
    confidence: float  # 0.0 - 1.0
    soundcloud_id: int
    permalink_url: str
    cached: bool = False
    resolved_at: Optional[datetime] = None


@dataclass
class CachedResult:
    """Cache entry for a resolved track"""
    youtube_video_id: str
    resolved_track: ResolvedTrack
    cached_at: datetime
    
    def is_expired(self, ttl_days: int = 7) -> bool:
        """Check if cache entry has expired"""
        age = datetime.now() - self.cached_at
        return age > timedelta(days=ttl_days)


class ResolverCache:
    """File-based cache for resolved tracks"""
    
    def __init__(self, cache_dir: str = "/tmp/cantio_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_days = 7
        logger.info(f"Cache initialized at {self.cache_dir}")
    
    def _get_cache_path(self, youtube_video_id: str) -> Path:
        """Get cache file path for a video ID"""
        # Use video ID as filename (safe characters only)
        safe_id = re.sub(r'[^a-zA-Z0-9_-]', '_', youtube_video_id)
        return self.cache_dir / f"{safe_id}.pkl"
    
    def get(self, youtube_video_id: str) -> Optional[ResolvedTrack]:
        """Retrieve cached resolution if available and not expired"""
        cache_path = self._get_cache_path(youtube_video_id)
        
        if not cache_path.exists():
            logger.debug(f"Cache MISS: {youtube_video_id}")
            return None
        
        try:
            with open(cache_path, 'rb') as f:
                cached: CachedResult = pickle.load(f)
            
            if cached.is_expired(self.ttl_days):
                logger.info(f"Cache EXPIRED: {youtube_video_id}")
                cache_path.unlink()  # Delete expired cache
                return None
            
            logger.info(f"Cache HIT: {youtube_video_id}")
            resolved = cached.resolved_track
            resolved.cached = True
            return resolved
            
        except Exception as e:
            logger.error(f"Cache read error for {youtube_video_id}: {e}")
            # Delete corrupted cache file
            try:
                cache_path.unlink()
            except:
                pass
            return None
    
    def set(self, youtube_video_id: str, resolved_track: ResolvedTrack):
        """Cache a successful resolution"""
        cache_path = self._get_cache_path(youtube_video_id)
        
        try:
            cached = CachedResult(
                youtube_video_id=youtube_video_id,
                resolved_track=resolved_track,
                cached_at=datetime.now()
            )
            
            with open(cache_path, 'wb') as f:
                pickle.dump(cached, f)
            
            logger.info(f"Cached resolution for {youtube_video_id}")
            
        except Exception as e:
            logger.error(f"Cache write error for {youtube_video_id}: {e}")
    
    def cleanup_expired(self) -> int:
        """Remove all expired cache entries"""
        removed = 0
        for cache_file in self.cache_dir.glob("*.pkl"):
            try:
                with open(cache_file, 'rb') as f:
                    cached: CachedResult = pickle.load(f)
                
                if cached.is_expired(self.ttl_days):
                    cache_file.unlink()
                    removed += 1
                    
            except Exception as e:
                # Delete corrupted files
                logger.warning(f"Removing corrupted cache file {cache_file}: {e}")
                try:
                    cache_file.unlink()
                    removed += 1
                except:
                    pass
        
        logger.info(f"Cleanup removed {removed} expired/corrupted cache entries")
        return removed
    
    def clear_all(self):
        """Clear entire cache"""
        removed = 0
        for cache_file in self.cache_dir.glob("*.pkl"):
            try:
                cache_file.unlink()
                removed += 1
            except Exception as e:
                logger.error(f"Failed to delete {cache_file}: {e}")
        
        logger.info(f"Cleared {removed} cache entries")
        return removed
    
    def get_stats(self) -> Dict:
        """Get cache statistics"""
        total = 0
        expired = 0
        valid = 0
        corrupted = 0
        total_size_bytes = 0
        
        for cache_file in self.cache_dir.glob("*.pkl"):
            total += 1
            total_size_bytes += cache_file.stat().st_size
            
            try:
                with open(cache_file, 'rb') as f:
                    cached: CachedResult = pickle.load(f)
                
                if cached.is_expired(self.ttl_days):
                    expired += 1
                else:
                    valid += 1
                    
            except:
                corrupted += 1
        
        return {
            "total_entries": total,
            "valid_entries": valid,
            "expired_entries": expired,
            "corrupted_entries": corrupted,
            "total_size_mb": round(total_size_bytes / (1024 * 1024), 2),
            "cache_ttl_days": self.ttl_days,
            "cache_dir": str(self.cache_dir)
        }


class TrackMatcher:
    """Intelligent track matching with scoring algorithm"""
    
    # Penalty values
    REMIX_PENALTY = 0.20
    DURATION_MISMATCH_PENALTY = 0.15
    LOW_PLAYCOUNT_PENALTY = 0.05
    
    # Thresholds
    MIN_CONFIDENCE = 0.70
    DURATION_TOLERANCE_SEC = 20
    LOW_PLAYCOUNT_THRESHOLD = 1000
    
    @staticmethod
    def normalize_string(text: str) -> str:
        """
        Normalize string for comparison.
        - Remove special characters and extra whitespace
        - Convert to lowercase
        - Remove common noise words
        - Handle Unicode characters
        """
        if not text:
            return ""
        
        # Normalize Unicode (é → e, ñ → n, etc.)
        text = unicodedata.normalize('NFKD', text)
        text = text.encode('ascii', 'ignore').decode('ascii')
        
        # Convert to lowercase
        text = text.lower()
        
        # Remove noise words and phrases
        noise_patterns = [
            r'\bofficial\b', r'\bvideo\b', r'\baudio\b', r'\blyrics?\b',
            r'\bhd\b', r'\b4k\b', r'\bmusic video\b', r'\bmv\b',
            r'\bft\.?\b', r'\bfeat\.?\b', r'\bfeaturing\b',
            r'\(.*?\)', r'\[.*?\]',  # Remove parentheses and brackets
        ]
        for pattern in noise_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        
        # Remove special characters except spaces and hyphens
        text = re.sub(r'[^\w\s-]', '', text)
        
        # Normalize whitespace
        text = ' '.join(text.split())
        
        return text.strip()
    
    @staticmethod
    def calculate_similarity(str1: str, str2: str) -> float:
        """Calculate string similarity using SequenceMatcher (0.0 - 1.0)"""
        if not str1 or not str2:
            return 0.0
        
        # Normalize both strings
        s1 = TrackMatcher.normalize_string(str1)
        s2 = TrackMatcher.normalize_string(str2)
        
        # Use SequenceMatcher for similarity ratio
        return SequenceMatcher(None, s1, s2).ratio()
    
    @staticmethod
    def has_remix_or_cover_tag(title: str) -> bool:
        """Check if title contains remix/cover/slowed tags"""
        title_lower = title.lower()
        tags = ['remix', 'cover', 'slowed', 'reverb', 'sped up', 'nightcore', 
                'acoustic', 'live', 'instrumental', 'karaoke']
        return any(tag in title_lower for tag in tags)
    
    @staticmethod
    def calculate_match_score(
        query_title: str,
        query_artist: str,
        query_duration: int,
        sc_title: str,
        sc_artist: str,
        sc_duration: int,
        sc_playcount: int = 0
    ) -> Tuple[float, Dict[str, float]]:
        """
        Calculate match score for a SoundCloud track.
        
        Returns: (final_score, breakdown_dict)
        final_score: 0.0 - 1.0 (higher is better)
        breakdown_dict: Component scores for debugging
        """
        breakdown = {}
        
        # 1. Title similarity (50% weight)
        title_sim = TrackMatcher.calculate_similarity(query_title, sc_title)
        breakdown['title_similarity'] = title_sim
        
        # 2. Artist match (30% weight)
        artist_sim = TrackMatcher.calculate_similarity(query_artist, sc_artist)
        breakdown['artist_similarity'] = artist_sim
        
        # 3. Duration proximity (20% weight)
        duration_diff = abs(sc_duration - query_duration)
        if duration_diff <= TrackMatcher.DURATION_TOLERANCE_SEC:
            duration_score = 1.0
        else:
            # Gradual penalty for duration mismatch
            duration_score = max(0.0, 1.0 - (duration_diff - TrackMatcher.DURATION_TOLERANCE_SEC) / 60.0)
        breakdown['duration_score'] = duration_score
        breakdown['duration_diff_sec'] = duration_diff
        
        # Calculate base score (weighted average)
        base_score = (
            title_sim * 0.5 +
            artist_sim * 0.3 +
            duration_score * 0.2
        )
        breakdown['base_score'] = base_score
        
        # Apply penalties
        penalties = 0.0
        
        # Penalty 1: Remix/cover in SC title but not in query
        query_has_tag = TrackMatcher.has_remix_or_cover_tag(query_title)
        sc_has_tag = TrackMatcher.has_remix_or_cover_tag(sc_title)
        if sc_has_tag and not query_has_tag:
            penalties += TrackMatcher.REMIX_PENALTY
            breakdown['remix_penalty'] = TrackMatcher.REMIX_PENALTY
        else:
            breakdown['remix_penalty'] = 0.0
        
        # Penalty 2: Large duration mismatch
        if duration_diff > TrackMatcher.DURATION_TOLERANCE_SEC:
            penalties += TrackMatcher.DURATION_MISMATCH_PENALTY
            breakdown['duration_penalty'] = TrackMatcher.DURATION_MISMATCH_PENALTY
        else:
            breakdown['duration_penalty'] = 0.0
        
        # Penalty 3: Low play count (unpopular tracks less likely to match)
        if sc_playcount is not None and sc_playcount < TrackMatcher.LOW_PLAYCOUNT_THRESHOLD:
            penalties += TrackMatcher.LOW_PLAYCOUNT_PENALTY
            breakdown['playcount_penalty'] = TrackMatcher.LOW_PLAYCOUNT_PENALTY
        else:
            breakdown['playcount_penalty'] = 0.0
        
        breakdown['total_penalties'] = penalties
        
        # Final score
        final_score = max(0.0, base_score - penalties)
        breakdown['final_score'] = final_score
        
        return final_score, breakdown


class TrackResolver:
    """Main resolver class for finding SoundCloud matches"""
    
    def __init__(self, cache: Optional[ResolverCache] = None):
        self.sc = SoundCloud()
        self.cache = cache or ResolverCache()
        self.matcher = TrackMatcher()
        logger.info("TrackResolver initialized")
    
    async def resolve(
        self,
        youtube_title: str,
        youtube_artist: str,
        youtube_duration: int,
        youtube_video_id: str
    ) -> Optional[ResolvedTrack]:
        """
        Resolve YouTube track to SoundCloud stream URL.
        
        Args:
            youtube_title: Track title from YouTube
            youtube_artist: Artist name from YouTube
            youtube_duration: Duration in seconds
            youtube_video_id: YouTube video ID (for caching)
        
        Returns:
            ResolvedTrack if match found with confidence >= threshold, else None
        """
        # Check cache first
        cached = self.cache.get(youtube_video_id)
        if cached:
            return cached
        
        # Build search query
        query = f"{youtube_title} {youtube_artist}".strip()
        logger.info(f"Resolving: {query} ({youtube_duration}s, ID: {youtube_video_id})")
        
        try:
            # Search SoundCloud (get top 20 results for better matching)
            logger.debug(f"Searching SoundCloud for: {query}")
            results = []
            count = 0
            for track in self.sc.search_tracks(query, limit=20):
                results.append(track)
                count += 1
                if count >= 20:
                    break
            
            if not results:
                logger.warning(f"No SoundCloud results for: {query}")
                return None
            
            logger.info(f"Found {len(results)} SoundCloud tracks")
            
            # Score all results
            scored_tracks = []
            for track in results:
                sc_duration = int(track.duration / 1000)  # Convert ms to seconds
                sc_playcount = getattr(track, 'playback_count', 0) or 0  # Handle None
                
                score, breakdown = self.matcher.calculate_match_score(
                    query_title=youtube_title,
                    query_artist=youtube_artist,
                    query_duration=youtube_duration,
                    sc_title=track.title,
                    sc_artist=track.user.username,
                    sc_duration=sc_duration,
                    sc_playcount=sc_playcount
                )
                
                scored_tracks.append((score, track, breakdown))
                logger.debug(f"  Score {score:.3f}: {track.title} by {track.user.username} ({sc_duration}s)")
            
            # Sort by score (highest first)
            scored_tracks.sort(key=lambda x: x[0], reverse=True)
            best_score, best_track, best_breakdown = scored_tracks[0]
            
            # Check confidence threshold
            if best_score < self.matcher.MIN_CONFIDENCE:
                logger.warning(
                    f"Best match confidence too low: {best_score:.3f} < {self.matcher.MIN_CONFIDENCE} "
                    f"for {query}"
                )
                return None
            
            # Get full track details with stream URL
            logger.info(f"Best match (confidence {best_score:.3f}): {best_track.title} by {best_track.user.username}")
            track_details = self.sc.get_track(best_track.id)
            
            # Extract stream URL
            stream_url = self._extract_stream_url(track_details)
            if not stream_url:
                logger.error(f"Failed to extract stream URL for track {best_track.id}")
                return None
            
            # Build resolved track
            resolved = ResolvedTrack(
                platform="soundcloud",
                stream_url=stream_url,
                title=track_details.title,
                artist=track_details.user.username,
                duration=int(track_details.duration / 1000),
                confidence=best_score,
                soundcloud_id=track_details.id,
                permalink_url=track_details.permalink_url,
                cached=False,
                resolved_at=datetime.now()
            )
            
            # Cache the result
            self.cache.set(youtube_video_id, resolved)
            
            logger.info(f"✓ Successfully resolved {youtube_video_id} to SoundCloud (confidence: {best_score:.3f})")
            return resolved
            
        except Exception as e:
            logger.error(f"Resolution error for {youtube_video_id}: {e}", exc_info=True)
            return None
    
    def _extract_stream_url(self, track) -> Optional[str]:
        """Extract stream URL from SoundCloud track object"""
        try:
            # Check if track has media with transcodings
            if not hasattr(track, 'media') or not track.media:
                logger.error("Track has no media attribute")
                return None
            
            transcodings = getattr(track.media, 'transcodings', [])
            if not transcodings:
                logger.error("Track has no transcodings")
                return None
            
            # Prefer progressive (direct download) over HLS
            progressive = None
            hls = None
            
            for t in transcodings:
                if hasattr(t, 'format') and hasattr(t.format, 'protocol'):
                    if t.format.protocol == 'progressive':
                        progressive = t
                    elif t.format.protocol == 'hls':
                        hls = t
            
            # Use progressive if available, otherwise HLS
            selected = progressive if progressive else hls
            
            if not selected:
                logger.error("No suitable transcoding found")
                return None
            
            # The URL in transcoding needs to be resolved with client_id
            # For now, return the transcoding URL - the client will need to resolve it
            stream_url = selected.url
            
            # Append client_id if not present
            if '?' in stream_url:
                stream_url += f"&client_id={self.sc.client_id}"
            else:
                stream_url += f"?client_id={self.sc.client_id}"
            
            logger.debug(f"Extracted stream URL: {stream_url[:100]}...")
            return stream_url
            
        except Exception as e:
            logger.error(f"Stream URL extraction error: {e}", exc_info=True)
            return None
