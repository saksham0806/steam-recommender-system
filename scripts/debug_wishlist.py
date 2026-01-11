"""
Debug wishlist sync to see what's happening

Usage:
    python scripts/debug_wishlist.py <steam_id>
"""

import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.steam_auth import steam_auth
from app.database import SessionLocal
from app.models.user import UserWishlist
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


async def debug_wishlist(steam_id: str):
    """Debug wishlist fetching"""
    
    print("=" * 60)
    print("Wishlist Debug Tool")
    print("=" * 60)
    print(f"Steam ID: {steam_id}\n")
    
    # Test 1: Try to fetch wishlist from Steam
    print("1. Attempting to fetch wishlist from Steam...")
    print(f"   URL: https://store.steampowered.com/wishlist/profiles/{steam_id}/wishlistdata/")
    
    wishlist_ids = await steam_auth.get_wishlist(steam_id)
    
    if wishlist_ids is None:
        print("   ✗ Failed to fetch wishlist (returned None)")
        print("   Possible reasons:")
        print("   - Network error")
        print("   - Steam API is down")
        print("   - Invalid Steam ID")
        return 1
    
    if not wishlist_ids:
        print("   ⚠ Wishlist is empty or private")
        print("\n   To make wishlist public:")
        print("   1. Go to Steam > Edit Profile > Privacy Settings")
        print("   2. Set 'My wishlist' to 'Public'")
        print("   3. Save and try again")
        return 1
    
    print(f"   ✓ Found {len(wishlist_ids)} wishlist items")
    print(f"   Sample IDs: {wishlist_ids[:5]}")
    
    # Test 2: Check database
    print("\n2. Checking database...")
    db = SessionLocal()
    
    try:
        existing_count = db.query(UserWishlist).filter(
            UserWishlist.steam_id == int(steam_id)
        ).count()
        
        print(f"   Current wishlist items in DB: {existing_count}")
        
        if existing_count > 0:
            print("   Existing items:")
            existing = db.query(UserWishlist).filter(
                UserWishlist.steam_id == int(steam_id)
            ).limit(5).all()
            
            for item in existing:
                print(f"     - Game ID: {item.game_id}")
        
        # Test 3: Try manual sync
        print("\n3. Attempting manual sync...")
        from app.services.library_sync import library_sync_service
        
        result = await library_sync_service.sync_wishlist(steam_id, db)
        
        print(f"   Sync result: {result}")
        
        # Test 4: Verify sync
        print("\n4. Verifying sync...")
        new_count = db.query(UserWishlist).filter(
            UserWishlist.steam_id == int(steam_id)
        ).count()
        
        print(f"   Wishlist items in DB after sync: {new_count}")
        
        if new_count > 0:
            print("   ✓ Wishlist synced successfully!")
            print("\n   Sample wishlist items:")
            items = db.query(UserWishlist).filter(
                UserWishlist.steam_id == int(steam_id)
            ).limit(5).all()
            
            for item in items:
                print(f"     - Game ID: {item.game_id}, Priority: {item.priority}")
        else:
            print("   ✗ Wishlist still empty in database")
            print("   This might be a bug - checking logs above for errors")
        
        return 0
        
    except Exception as e:
        logger.error(f"Error during debug: {e}", exc_info=True)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/debug_wishlist.py <steam_id>")
        sys.exit(1)
    
    steam_id = sys.argv[1]
    exit_code = asyncio.run(debug_wishlist(steam_id))
    sys.exit(exit_code)