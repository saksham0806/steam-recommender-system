"""
Update tags for ALL games by scraping Steam store pages
This will refresh tags even for games that already have some tags
"""

import asyncio
import sys
from pathlib import Path
import httpx
import re

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import SessionLocal
from app.models.game import Game
import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def scrape_tags_from_store(app_id: int) -> list:
    """Scrape popular tags from Steam store page"""
    url = f"https://store.steampowered.com/app/{app_id}"
    
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(10.0),
            follow_redirects=True
        ) as client:
            response = await client.get(url)
            
            if response.status_code != 200:
                return []
            
            html = response.text
            
            # Method 1: Find tags in app_tag links
            tag_pattern = r'<a[^>]*class="app_tag"[^>]*>\s*([^<]+?)\s*</a>'
            matches = re.findall(tag_pattern, html)
            
            if matches:
                # Clean and deduplicate
                tags = []
                seen = set()
                for tag in matches:
                    tag = tag.strip()
                    if tag and tag not in seen and len(tag) < 50:
                        tags.append(tag)
                        seen.add(tag)
                
                return tags[:15]  # Top 15 tags
            
            # Method 2: Try data-tag-name attributes
            tag_pattern2 = r'data-tag-name="([^"]+)"'
            matches2 = re.findall(tag_pattern2, html)
            
            if matches2:
                tags = []
                seen = set()
                for tag in matches2:
                    tag = tag.strip()
                    if tag and tag not in seen and len(tag) < 50:
                        tags.append(tag)
                        seen.add(tag)
                
                return tags[:15]
            
            return []
            
    except Exception as e:
        logger.debug(f"Failed to scrape tags for {app_id}: {e}")
        return []


async def update_all_tags(limit: int = None, skip_with_many_tags: bool = False):
    """
    Update tags for all games
    
    Args:
        limit: Max number of games to update (None = all)
        skip_with_many_tags: If True, skip games that already have 5+ tags
    """
    
    db = SessionLocal()
    
    try:
        # Get all games
        query = db.query(Game).filter(Game.data_complete == True)
        
        if skip_with_many_tags:
            # Skip games that already have good tag data
            all_games = query.all()
            games_to_update = [
                g for g in all_games 
                if not g.tags or len(g.tags) < 5
            ]
        else:
            games_to_update = query.all()
        
        if limit:
            games_to_update = games_to_update[:limit]
        
        total = len(games_to_update)
        logger.info(f"Found {total:,} games to update")
        
        if total == 0:
            logger.info("No games to update!")
            return
        
        logger.info(f"Starting tag collection...")
        logger.info(f"Estimated time: {total * 2 / 60:.1f} minutes (2s per game)")
        logger.info("=" * 60)
        
        updated = 0
        failed = 0
        unchanged = 0
        
        for i, game in enumerate(games_to_update):
            try:
                current_tags = len(game.tags) if game.tags else 0
                
                # Progress indicator
                if (i + 1) % 10 == 0:
                    progress = (i + 1) / total * 100
                    logger.info(
                        f"Progress: {i+1:,}/{total:,} ({progress:.1f}%) | "
                        f"Updated: {updated} | Failed: {failed}"
                    )
                
                logger.info(f"[{i+1}/{total}] {game.name} (ID: {game.id})")
                logger.info(f"  Current tags: {current_tags}")
                
                # Scrape tags
                tags = await scrape_tags_from_store(game.id)
                
                if tags:
                    old_count = len(game.tags) if game.tags else 0
                    game.tags = tags
                    db.commit()
                    updated += 1
                    logger.info(f"  ✓ Updated: {old_count} → {len(tags)} tags")
                    logger.info(f"    Tags: {', '.join(tags[:5])}")
                else:
                    failed += 1
                    logger.info(f"  ✗ No tags found")
                
                # Rate limiting to avoid being blocked
                await asyncio.sleep(2)
                
                # Extra delay every 50 requests
                if (i + 1) % 50 == 0:
                    logger.info("  ⏸️  Taking 10s break to avoid rate limiting...")
                    await asyncio.sleep(10)
                
            except KeyboardInterrupt:
                logger.info("\n⚠️  Interrupted! Saving progress...")
                db.commit()
                break
            except Exception as e:
                logger.error(f"  ✗ Error: {e}")
                failed += 1
                continue
        
        logger.info("=" * 60)
        logger.info("✓ Tag Update Complete!")
        logger.info("=" * 60)
        logger.info(f"Total processed: {i+1:,}")
        logger.info(f"Successfully updated: {updated:,}")
        logger.info(f"Failed: {failed}")
        logger.info(f"Unchanged: {unchanged}")
        logger.info("=" * 60)
        
        # Show sample of updated games
        logger.info("\nSample of games with tags:")
        sample = db.query(Game).filter(
            Game.tags != None,
            Game.tags != []
        ).limit(5).all()
        
        for game in sample:
            logger.info(f"  {game.name}: {len(game.tags)} tags")
            logger.info(f"    {', '.join(game.tags[:5])}")
        
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Update Steam game tags')
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Limit number of games to update (default: all)'
    )
    parser.add_argument(
        '--skip-complete',
        action='store_true',
        help='Skip games that already have 5+ tags'
    )
    
    args = parser.parse_args()
    
    print(f"\n{'='*60}")
    print("STEAM GAME TAG UPDATER")
    print(f"{'='*60}")
    
    if args.limit:
        print(f"Updating: {args.limit:,} games")
    else:
        print("Updating: ALL games in database")
    
    if args.skip_complete:
        print("Mode: Only update games with <5 tags")
    else:
        print("Mode: Update all games (refresh existing tags)")
    
    print(f"{'='*60}\n")
    
    response = input("Continue? (y/n): ")
    if response.lower() != 'y':
        print("Cancelled.")
        sys.exit(0)
    
    asyncio.run(update_all_tags(
        limit=args.limit,
        skip_with_many_tags=args.skip_complete
    ))
