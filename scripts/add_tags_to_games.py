import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import SessionLocal
from app.models.game import Game
from app.services.tag_scraper import scrape_tags_from_store
import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def add_tags_to_games(limit: int = 100):
    """Add tags to games that don't have them"""
    
    db = SessionLocal()
    
    try:
        # Get games without tags
        games_without_tags = db.query(Game).filter(
            Game.data_complete == True,
            Game.tags == None
        ).limit(limit).all()
        
        logger.info(f"Found {len(games_without_tags)} games without tags")
        logger.info(f"Adding tags to {min(limit, len(games_without_tags))} games...")
        
        updated = 0
        
        for i, game in enumerate(games_without_tags):
            try:
                logger.info(f"[{i+1}/{len(games_without_tags)}] {game.name}...")
                
                tags = await scrape_tags_from_store(game.id)
                
                if tags:
                    game.tags = tags
                    db.commit()
                    updated += 1
                    logger.info(f"  ✓ Added {len(tags)} tags: {', '.join(tags[:3])}")
                else:
                    logger.info(f"  ✗ No tags found")
                
                # Rate limiting
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"Error processing {game.name}: {e}")
                continue
        
        logger.info(f"\n✓ Updated {updated} games with tags")
        
    finally:
        db.close()


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    asyncio.run(add_tags_to_games(limit))