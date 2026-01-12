"""
Update genres for ALL games using Steam Store API
This will refresh genre data for all games in the database
"""

import asyncio
import sys
from pathlib import Path
import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import SessionLocal
from app.models.game import Game
import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def fetch_game_genres(app_id: int) -> dict:
    """
    Fetch game details including genres from Steam API
    """
    url = "https://store.steampowered.com/api/appdetails"
    params = {'appids': app_id, 'cc': 'us', 'l': 'english'}
    
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            follow_redirects=True
        ) as client:
            response = await client.get(url, params=params)
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            app_data = data.get(str(app_id), {})
            
            if not app_data.get('success', False):
                return None
            
            game_data = app_data.get('data', {})
            
            # Extract genres
            genres = [g['description'] for g in game_data.get('genres', [])]
            
            # Extract categories (useful info too)
            categories = [c['description'] for c in game_data.get('categories', [])]
            
            # Extract other useful metadata
            result = {
                'genres': genres,
                'categories': categories,
                'developers': game_data.get('developers', []),
                'publishers': game_data.get('publishers', []),
            }
            
            return result
            
    except Exception as e:
        logger.debug(f"Failed to fetch data for {app_id}: {e}")
        return None


async def update_all_genres(limit: int = None, skip_with_genres: bool = False):
    """
    Update genres for all games
    
    Args:
        limit: Max number of games to update (None = all)
        skip_with_genres: If True, skip games that already have 2+ genres
    """
    
    db = SessionLocal()
    
    try:
        # Get all games
        query = db.query(Game).filter(Game.data_complete == True)
        
        if skip_with_genres:
            # Skip games that already have good genre data
            all_games = query.all()
            games_to_update = [
                g for g in all_games 
                if not g.genres or len(g.genres) < 2
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
        
        logger.info(f"Starting genre/metadata collection...")
        logger.info(f"Estimated time: {total * 1.5 / 60:.1f} minutes (1.5s per game)")
        logger.info("=" * 60)
        
        updated = 0
        failed = 0
        skipped = 0
        
        for i, game in enumerate(games_to_update):
            try:
                current_genres = len(game.genres) if game.genres else 0
                
                # Progress indicator
                if (i + 1) % 10 == 0:
                    progress = (i + 1) / total * 100
                    logger.info(
                        f"Progress: {i+1:,}/{total:,} ({progress:.1f}%) | "
                        f"Updated: {updated} | Failed: {failed} | Skipped: {skipped}"
                    )
                
                logger.info(f"[{i+1}/{total}] {game.name} (ID: {game.id})")
                logger.info(f"  Current genres: {current_genres} - {game.genres or []}")
                
                # Fetch updated data
                game_data = await fetch_game_genres(game.id)
                
                if game_data:
                    genres = game_data['genres']
                    categories = game_data['categories']
                    developers = game_data['developers']
                    publishers = game_data['publishers']
                    
                    if genres:
                        old_genre_count = len(game.genres) if game.genres else 0
                        
                        # Update all fields
                        game.genres = genres
                        game.categories = categories
                        game.developers = developers
                        game.publishers = publishers
                        
                        db.commit()
                        updated += 1
                        
                        logger.info(f"  ✓ Updated: {old_genre_count} → {len(genres)} genres")
                        logger.info(f"    Genres: {', '.join(genres)}")
                        if categories:
                            logger.info(f"    Categories: {', '.join(categories[:3])}")
                    else:
                        skipped += 1
                        logger.info(f"  ⚠ No genres found (may not be a game)")
                else:
                    failed += 1
                    logger.info(f"  ✗ Failed to fetch data")
                
                # Rate limiting
                await asyncio.sleep(1.5)
                
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
                db.rollback()
                continue
        
        logger.info("=" * 60)
        logger.info("✓ Genre Update Complete!")
        logger.info("=" * 60)
        logger.info(f"Total processed: {i+1:,}")
        logger.info(f"Successfully updated: {updated:,}")
        logger.info(f"Failed: {failed}")
        logger.info(f"Skipped (no genres): {skipped}")
        logger.info("=" * 60)
        
        # Show statistics
        logger.info("\nGenre Statistics:")
        
        from sqlalchemy import func
        
        # Count games by genre count
        genre_counts = db.query(
            func.array_length(Game.genres, 1).label('count'),
            func.count(Game.id)
        ).filter(
            Game.genres != None
        ).group_by('count').order_by('count').all()
        
        for count, num_games in genre_counts:
            logger.info(f"  Games with {count} genres: {num_games}")
        
        # Show sample
        logger.info("\nSample of updated games:")
        sample = db.query(Game).filter(
            Game.genres != None,
            func.array_length(Game.genres, 1) > 1
        ).limit(5).all()
        
        for game in sample:
            logger.info(f"  {game.name}:")
            logger.info(f"    Genres: {', '.join(game.genres)}")
            if game.categories:
                logger.info(f"    Categories: {', '.join(game.categories[:3])}")
        
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Update Steam game genres and metadata')
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Limit number of games to update (default: all)'
    )
    parser.add_argument(
        '--skip-complete',
        action='store_true',
        help='Skip games that already have 2+ genres'
    )
    
    args = parser.parse_args()
    
    print(f"\n{'='*60}")
    print("STEAM GAME GENRE & METADATA UPDATER")
    print(f"{'='*60}")
    
    if args.limit:
        print(f"Updating: {args.limit:,} games")
    else:
        print("Updating: ALL games in database")
    
    if args.skip_complete:
        print("Mode: Only update games with <2 genres")
    else:
        print("Mode: Update all games (refresh existing data)")
    
    print(f"{'='*60}\n")
    
    response = input("Continue? (y/n): ")
    if response.lower() != 'y':
        print("Cancelled.")
        sys.exit(0)
    
    asyncio.run(update_all_genres(
        limit=args.limit,
        skip_with_genres=args.skip_complete
    ))
