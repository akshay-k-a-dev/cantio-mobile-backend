#!/usr/bin/env python3
"""
Quick test of the track resolver before deployment.
"""
import asyncio
import sys
from track_resolver import TrackResolver, ResolverCache

async def test_resolver():
    """Test resolver with known track"""
    print("=" * 70)
    print("TRACK RESOLVER TEST")
    print("=" * 70)
    
    try:
        # Initialize
        print("\n[1/3] Initializing resolver...")
        cache = ResolverCache(cache_dir="/tmp/cantio_test_cache")
        resolver = TrackResolver(cache=cache)
        print("✓ Resolver initialized")
        
        # Test track: "back to friends" by sombr
        print("\n[2/3] Resolving test track...")
        print("  Title: back to friends")
        print("  Artist: sombr")
        print("  Duration: 202s")
        print("  Video ID: c8zq4kAn_O0")
        
        resolved = await resolver.resolve(
            youtube_title="back to friends",
            youtube_artist="sombr",
            youtube_duration=202,
            youtube_video_id="c8zq4kAn_O0"
        )
        
        if resolved:
            print(f"\n✓ RESOLUTION SUCCESSFUL!")
            print(f"  Platform: {resolved.platform}")
            print(f"  Title: {resolved.title}")
            print(f"  Artist: {resolved.artist}")
            print(f"  Duration: {resolved.duration}s")
            print(f"  Confidence: {resolved.confidence:.3f}")
            print(f"  SoundCloud ID: {resolved.soundcloud_id}")
            print(f"  Permalink: {resolved.permalink_url}")
            print(f"  Stream URL: {resolved.stream_url[:100]}...")
            print(f"  Cached: {resolved.cached}")
            
            # Test cache
            print("\n[3/3] Testing cache...")
            resolved2 = await resolver.resolve(
                youtube_title="back to friends",
                youtube_artist="sombr",
                youtube_duration=202,
                youtube_video_id="c8zq4kAn_O0"
            )
            
            if resolved2 and resolved2.cached:
                print("✓ Cache working correctly!")
            else:
                print("⚠ Cache not working as expected")
            
            print("\n" + "=" * 70)
            print("✓ ALL TESTS PASSED - Resolver is ready!")
            print("=" * 70)
            return True
        else:
            print("\n✗ RESOLUTION FAILED - No match found")
            return False
            
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_resolver())
    sys.exit(0 if success else 1)
