"""
Test Steam authentication and library sync

Usage:
    python scripts/test_auth.py <steam_id>
    
Example:
    python scripts/test_auth.py 76561198012345678
"""

import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import SessionLocal
from app.services.steam_auth import steam_auth
from app.services.library_sync import library_sync_service
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_authentication(steam_id: str):
    """Test Steam API authentication and library fetching"""
    
    logger.info("=" * 60)
    logger.info("Testing Steam Authentication & Library Sync")
    logger.info("=" * 60)
    logger.info(f"Steam ID: {steam_id}\n")
    
    db = SessionLocal()
    
    try:
        # Test 1: Fetch player summaries
        logger.info("1. Fetching player profile...")
        player_data = await steam_auth.get_player_summaries(steam_id)
        
        if player_data:
            logger.info(f"✓ Profile found:")
            logger.info(f"  Name: {player_data.get('personaname')}")
            logger.info(f"  Profile: {player_data.get('profileurl')}")
            logger.info(f"  Country: {player_data.get('loccountrycode', 'Unknown')}")
        else:
            logger.warning("✗ Could not fetch profile (check STEAM_API_KEY)")
        
        # Test 2: Fetch owned games
        logger.info("\n2. Fetching owned games...")
        games_data = await steam_auth.get_owned_games(steam_id)
        
        if games_data:
            game_count = games_data.get('game_count', 0)
            logger.info(f"✓ Found {game_count} owned games")
            
            if game_count > 0:
                # Show sample games
                games = games_data.get('games', [])[:5]
                logger.info("  Sample games:")
                for game in games:
                    playtime_hours = game.get('playtime_forever', 0) / 60.0
                    logger.info(f"    - {game.get('name')} ({playtime_hours:.1f}h)")
        else:
            logger.warning("✗ Could not fetch games")
        
        # Test 3: Fetch wishlist
        logger.info("\n3. Fetching wishlist...")
        wishlist_ids = await steam_auth.get_wishlist(steam_id)
        
        if wishlist_ids is not None:
            logger.info(f"✓ Found {len(wishlist_ids)} wishlist items")
            if wishlist_ids:
                logger.info(f"  Sample IDs: {wishlist_ids[:5]}")
        else:
            logger.warning("✗ Could not fetch wishlist (may be private)")
        
        # Test 4: Full sync
        logger.info("\n4. Performing full library sync...")
        result = await library_sync_service.full_sync(steam_id, db)
        
        logger.info(f"✓ Sync completed:")
        logger.info(f"  User: {result.get('user_name')}")
        logger.info(f"  Games added: {result.get('games_added')}")
        logger.info(f"  Games updated: {result.get('games_updated')}")
        logger.info(f"  Total games: {result.get('total_games')}")
        logger.info(f"  Wishlist items: {result.get('wishlist_synced')}")
        
        logger.info("\n" + "=" * 60)
        logger.info("✓ All tests passed!")
        logger.info("=" * 60)
        logger.info("\nYou can now:")
        logger.info(f"  - View profile: curl http://localhost:8000/api/v1/users/{steam_id}")
        logger.info(f"  - View library: curl http://localhost:8000/api/v1/users/{steam_id}/library")
        logger.info(f"  - View stats: curl http://localhost:8000/api/v1/users/{steam_id}/stats")
        
        return 0
        
    except Exception as e:
        logger.error(f"\n✗ Test failed: {e}", exc_info=True)
        return 1
    finally:
        db.close()


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_auth.py <steam_id>")
        print("\nTo find your Steam ID:")
        print("1. Go to https://steamcommunity.com/my/profile")
        print("2. Your Steam ID is in the URL")
        print("   Example: steamcommunity.com/profiles/76561198012345678")
        print("            Your ID is: 76561198012345678")
        sys.exit(1)
    
    steam_id = sys.argv[1]
    
    # Validate Steam ID format
    if not steam_id.isdigit() or len(steam_id) != 17:
        print(f"Error: Invalid Steam ID format: {steam_id}")
        print("Steam ID should be 17 digits")
        sys.exit(1)
    
    exit_code = asyncio.run(test_authentication(steam_id))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()