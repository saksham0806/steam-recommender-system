"""
Initial game collection script.
Run this once to populate your database with Steam games.

Usage:
    python scripts/collect_games.py
    
Optional arguments:
    --max-games: Maximum number of games to collect (default: 20000)
    --batch-size: Number of games to save at once (default: 100)
"""

import asyncio
import sys
import argparse
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import SessionLocal
from app.services.steam_collector_v2 import steam_collector_v2
from app.config import settings
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main(max_games: int, batch_size: int):
    """Main collection function"""
    logger.info("=" * 60)
    logger.info("Steam Game Collection Script")
    logger.info("=" * 60)
    logger.info(f"Max games to collect: {max_games}")
    logger.info(f"Batch size: {batch_size}")
    logger.info("=" * 60)
    
    # Update settings
    settings.MAX_GAMES_TO_COLLECT = max_games
    settings.BATCH_SIZE = batch_size
    
    # Create database session
    db = SessionLocal()
    
    try:
        # Start collection using enhanced collector
        collected, failed = await steam_collector_v2.collect_popular_games(
            db=db,
            max_games=max_games
        )
        
        logger.info("=" * 60)
        logger.info("Collection Summary")
        logger.info("=" * 60)
        logger.info(f"Successfully collected: {collected} games")
        logger.info(f"Failed to collect: {failed} games")
        logger.info(f"Success rate: {(collected/(collected+failed)*100):.2f}%")
        logger.info("=" * 60)
        
        # Print some sample data
        from app.models.game import Game
        sample_games = db.query(Game).limit(5).all()
        
        if sample_games:
            logger.info("\nSample games in database:")
            for game in sample_games:
                logger.info(f"  - {game.name} (${game.price_usd or 'Free'})")
        
    except Exception as e:
        logger.error(f"Collection failed with error: {e}", exc_info=True)
        return 1
    finally:
        db.close()
    
    logger.info("\n✓ Collection complete! You can now start the API server.")
    logger.info("  Run: uvicorn app.main:app --reload")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Collect Steam game data')
    parser.add_argument(
        '--max-games',
        type=int,
        default=20000,
        help='Maximum number of games to collect (default: 20000)'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=100,
        help='Batch size for database inserts (default: 100)'
    )
    
    args = parser.parse_args()
    
    # Run async main
    exit_code = asyncio.run(main(args.max_games, args.batch_size))
    sys.exit(exit_code)