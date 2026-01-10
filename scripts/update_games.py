"""
Update script for refreshing game data.
Run this periodically (e.g., weekly via cron) to update prices and game details.

Usage:
    python scripts/update_games.py
    
Optional arguments:
    --limit: Number of games to update (default: all)
    --oldest-first: Update oldest games first (default: True)
"""

import asyncio
import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import SessionLocal
from app.services.steam_collector import steam_collector
from app.models.game import Game
from sqlalchemy import func
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def update_games(limit: int = None, oldest_first: bool = True):
    """Update existing games in the database"""
    db = SessionLocal()
    
    try:
        # Query games to update
        query = db.query(Game)
        
        if oldest_first:
            query = query.order_by(Game.last_updated.asc())
        else:
            query = query.order_by(Game.last_updated.desc())
        
        if limit:
            games_to_update = query.limit(limit).all()
        else:
            games_to_update = query.all()
        
        total_games = len(games_to_update)
        logger.info(f"Updating {total_games} games...")
        
        updated = 0
        failed = 0
        
        for i, game in enumerate(games_to_update):
            try:
                # Fetch fresh data
                details = await steam_collector.get_app_details(game.id)
                
                if details:
                    # Parse updated data
                    updated_data = steam_collector.parse_game_data(game.id, details)
                    
                    if updated_data:
                        # Update game fields
                        for key, value in updated_data.items():
                            if key != 'id':  # Don't update primary key
                                setattr(game, key, value)
                        
                        updated += 1
                    else:
                        failed += 1
                else:
                    failed += 1
                
                # Commit every 50 games
                if (i + 1) % 50 == 0:
                    db.commit()
                    logger.info(f"Progress: {i + 1}/{total_games} games processed")
                
                # Rate limiting
                if i % 10 == 0:
                    await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Error updating game {game.id}: {e}")
                failed += 1
        
        # Final commit
        db.commit()
        
        logger.info("=" * 60)
        logger.info("Update Summary")
        logger.info("=" * 60)
        logger.info(f"Successfully updated: {updated} games")
        logger.info(f"Failed to update: {failed} games")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Update failed: {e}", exc_info=True)
        db.rollback()
        return 1
    finally:
        db.close()
    
    return 0


async def main(limit: int, oldest_first: bool):
    """Main update function"""
    logger.info("=" * 60)
    logger.info("Steam Game Update Script")
    logger.info("=" * 60)
    logger.info(f"Games to update: {'All' if not limit else limit}")
    logger.info(f"Update order: {'Oldest first' if oldest_first else 'Newest first'}")
    logger.info("=" * 60)
    
    exit_code = await update_games(limit=limit, oldest_first=oldest_first)
    
    if exit_code == 0:
        logger.info("\n✓ Update complete!")
    
    return exit_code


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Update Steam game data')
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Number of games to update (default: all)'
    )
    parser.add_argument(
        '--oldest-first',
        action='store_true',
        default=True,
        help='Update oldest games first (default: True)'
    )
    
    args = parser.parse_args()
    
    exit_code = asyncio.run(main(args.limit, args.oldest_first))
    sys.exit(exit_code)