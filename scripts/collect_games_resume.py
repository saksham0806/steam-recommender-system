"""
Resume-capable game collection script using complete Steam API.
This version can collect 10,000+ games from the full Steam catalog.

Usage:
    python scripts/collect_games_resume.py --max-games 5000
    
Features:
- Uses complete Steam app list (150,000+ apps)
- Skips already collected games
- Shows time estimates
- Can be safely interrupted (Ctrl+C)
- Automatically resumes from last position
"""

import asyncio
import sys
import argparse
from pathlib import Path
import signal

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import SessionLocal
from app.services.steam_collector_v2 import steam_collector_v2
from app.models.game import Game
from app.config import settings
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global flag for graceful shutdown
shutdown_requested = False


def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    global shutdown_requested
    logger.info("\n⚠️  Shutdown requested. Finishing current batch...")
    logger.info("Press Ctrl+C again to force quit (may lose current batch)")
    shutdown_requested = True


async def collect_with_resume(max_games: int, batch_size: int):
    """Main collection function with resume capability"""
    
    # Register signal handler
    signal.signal(signal.SIGINT, signal_handler)
    
    logger.info("=" * 60)
    logger.info("Steam Game Collection (Complete API)")
    logger.info("=" * 60)
    logger.info(f"Target: {max_games:,} games")
    logger.info(f"Using complete Steam app list (150k+ apps available)")
    logger.info(f"Rate limiting: ~1.5s per game + periodic cooldowns")
    logger.info(f"Press Ctrl+C once to gracefully stop")
    logger.info("=" * 60)
    
    db = SessionLocal()
    
    try:
        # Check existing games
        existing_count = db.query(Game).filter(Game.data_complete == True).count()
        logger.info(f"📊 Current database: {existing_count:,} games")
        
        # Get existing game IDs
        existing_ids = set(
            db.query(Game.id)
            .filter(Game.data_complete == True)
            .all()
        )
        existing_ids = {id[0] for id in existing_ids}
        logger.info(f"📋 Will skip {len(existing_ids):,} already collected games")
        
        # Get COMPLETE app list from Steam
        logger.info("🔍 Fetching complete Steam app list...")
        all_apps = await steam_collector_v2.get_complete_app_list()
        
        if not all_apps:
            logger.error("❌ Could not fetch app list from Steam")
            return 1
        
        logger.info(f"✓ Retrieved {len(all_apps):,} total apps from Steam")
        
        # Get popular game IDs to prioritize
        popular_ids = await steam_collector_v2.get_popular_app_ids()
        
        # Prioritize: popular games first, then rest
        apps_dict = {app['appid']: app for app in all_apps}
        prioritized_apps = []
        
        # Add popular games first
        for app_id in popular_ids:
            if app_id in apps_dict and app_id not in existing_ids:
                prioritized_apps.append(apps_dict[app_id])
                del apps_dict[app_id]
        
        # Add remaining apps (filter out already collected)
        for app in apps_dict.values():
            if app['appid'] not in existing_ids:
                prioritized_apps.append(app)
                if len(prioritized_apps) >= max_games:
                    break
        
        apps_to_collect = prioritized_apps[:max_games]
        
        if not apps_to_collect:
            logger.info("✅ All requested games already collected!")
            logger.info(f"Current database has {existing_count:,} games")
            logger.info("Increase --max-games to collect more")
            return 0
        
        logger.info(f"🎮 {len(apps_to_collect):,} new games to collect")
        estimated_time = len(apps_to_collect) * 1.5 / 60
        logger.info(f"⏱️  Estimated time: {estimated_time:.1f} minutes")
        logger.info("=" * 60)
        
        collected = 0
        failed = 0
        skipped = 0
        batch = []
        
        for i, app in enumerate(apps_to_collect):
            # Check for shutdown request
            if shutdown_requested:
                logger.info("💾 Saving current batch before shutdown...")
                if batch:
                    steam_collector_v2._save_batch(db, batch)
                logger.info(f"✅ Saved progress. Run script again to continue.")
                logger.info(f"Collected: {collected:,} | Failed: {failed}")
                break
            
            app_id = app['appid']
            
            # Double-check not already in DB (in case of concurrent runs)
            if db.query(Game).filter(Game.id == app_id).first():
                skipped += 1
                continue
            
            try:
                # Fetch and process game
                details = await steam_collector_v2.get_app_details(app_id)
                
                if details:
                    game_data = steam_collector_v2.parse_game_data(app_id, details)
                    
                    if game_data:
                        batch.append(game_data)
                        collected += 1
                        
                        # Save batch
                        if len(batch) >= batch_size:
                            steam_collector_v2._save_batch(db, batch)
                            batch = []
                            
                            # Progress with ETA
                            remaining = len(apps_to_collect) - (i + 1)
                            eta_minutes = remaining * 1.5 / 60
                            success_rate = (collected / (collected + failed)) * 100 if (collected + failed) > 0 else 0
                            logger.info(
                                f"✓ {collected:,}/{len(apps_to_collect):,} collected | "
                                f"{failed} failed | "
                                f"Success: {success_rate:.1f}% | "
                                f"ETA: {eta_minutes:.1f}m"
                            )
                    else:
                        failed += 1
                else:
                    failed += 1
                    
            except KeyboardInterrupt:
                # Second Ctrl+C - force quit
                logger.warning("⚠️  Force quit requested!")
                raise
            except Exception as e:
                logger.error(f"Error on {app_id}: {e}")
                failed += 1
            
            # Progress every 50 games
            if (i + 1) % 50 == 0:
                progress = ((i + 1) / len(apps_to_collect)) * 100
                logger.info(f"📈 Progress: {progress:.1f}% ({i + 1:,}/{len(apps_to_collect):,})")
        
        # Save remaining
        if batch:
            steam_collector_v2._save_batch(db, batch)
        
        # Final summary
        logger.info("=" * 60)
        logger.info("✅ Collection Session Complete!")
        logger.info("=" * 60)
        logger.info(f"   New games collected: {collected:,}")
        logger.info(f"   Failed: {failed}")
        logger.info(f"   Skipped (already in DB): {skipped}")
        logger.info(f"   Total in database: {existing_count + collected:,}")
        logger.info("=" * 60)
        
        if collected + existing_count < max_games:
            remaining = max_games - (collected + existing_count)
            logger.info(f"💡 Want more? Run again to collect {remaining:,} more games")
        else:
            logger.info(f"🎉 Target reached! You now have {existing_count + collected:,} games")
        
        return 0
        
    except KeyboardInterrupt:
        logger.info("\n⚠️  Interrupted! Progress has been saved.")
        return 130
    except Exception as e:
        logger.error(f"❌ Collection failed: {e}", exc_info=True)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Collect Steam games with resume capability (Complete API)'
    )
    parser.add_argument(
        '--max-games',
        type=int,
        default=2000,
        help='Target number of games (default: 2000, can go up to 100k+)'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=50,
        help='Save progress every N games (default: 50)'
    )
    
    args = parser.parse_args()
    
    # Update settings
    settings.BATCH_SIZE = args.batch_size
    
    # Validate
    if args.max_games > 50000:
        print(f"Warning: {args.max_games:,} is a lot of games!")
        print(f"This will take approximately {args.max_games * 1.5 / 3600:.1f} hours")
        response = input("Continue? (y/n): ")
        if response.lower() != 'y':
            sys.exit(0)
    
    exit_code = asyncio.run(collect_with_resume(args.max_games, args.batch_size))
    sys.exit(exit_code)