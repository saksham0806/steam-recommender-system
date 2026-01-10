import httpx
import asyncio
from typing import List, Dict, Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from app.models.game import Game
from app.config import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SteamCollectorV2:
    """
    Enhanced service for collecting game data from Steam.
    Uses multiple data sources: Steam API, SteamSpy, and Steam Store.
    """
    
    def __init__(self):
        self.steam_api = "https://api.steampowered.com"
        self.steam_store = "https://store.steampowered.com/api"
        self.steamspy_api = "https://steamspy.com/api.php"
        self.timeout = httpx.Timeout(30.0)
        self.request_count = 0
        self.last_request_time = 0
        
    async def get_app_list_from_steamspy(self, limit: int = 1000) -> List[Dict]:
        """
        Get top games from SteamSpy (reliable alternative).
        SteamSpy provides data on most popular games by player count.
        """
        logger.info("Fetching game list from SteamSpy...")
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                # Get top games by players
                response = await client.get(
                    self.steamspy_api,
                    params={'request': 'top100in2weeks'}
                )
                response.raise_for_status()
                data = response.json()
                
                apps = []
                for appid, game_data in data.items():
                    if appid.isdigit():
                        apps.append({
                            'appid': int(appid),
                            'name': game_data.get('name', f'Game_{appid}')
                        })
                
                logger.info(f"Retrieved {len(apps)} games from SteamSpy top100")
                
                # If we need more, get the full list
                if limit > 100:
                    response = await client.get(
                        self.steamspy_api,
                        params={'request': 'all'}
                    )
                    if response.status_code == 200:
                        all_data = response.json()
                        for appid, game_data in all_data.items():
                            if appid.isdigit() and int(appid) not in [a['appid'] for a in apps]:
                                apps.append({
                                    'appid': int(appid),
                                    'name': game_data.get('name', f'Game_{appid}')
                                })
                                if len(apps) >= limit:
                                    break
                
                logger.info(f"Total apps from SteamSpy: {len(apps)}")
                return apps[:limit]
                
            except Exception as e:
                logger.error(f"Failed to fetch from SteamSpy: {e}")
                return []
    
    async def _rate_limit_wait(self):
        """
        Intelligent rate limiting to avoid 429 errors.
        Steam allows ~200 requests per 5 minutes.
        """
        import time
        
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        # Ensure minimum delay between requests
        min_delay = 1.5  # 1.5 seconds between requests
        if time_since_last < min_delay:
            await asyncio.sleep(min_delay - time_since_last)
        
        # Track requests and add cooldown every 50 requests
        self.request_count += 1
        if self.request_count % 50 == 0:
            logger.info(f"Rate limit cooldown after {self.request_count} requests...")
            await asyncio.sleep(10)  # 10 second cooldown
        
        # Longer cooldown every 150 requests
        if self.request_count % 150 == 0:
            logger.info(f"Extended cooldown after {self.request_count} requests...")
            await asyncio.sleep(30)  # 30 second cooldown
        
        self.last_request_time = time.time()
    
    @retry(
        stop=stop_after_attempt(5),  # More retries
        wait=wait_exponential(multiplier=2, min=4, max=60)  # Longer waits
    )
    async def get_app_details(self, app_id: int) -> Optional[Dict]:
        """
        Fetch detailed information for a specific app from Steam Store.
        Includes intelligent rate limiting.
        """
        # Rate limiting before request
        await self._rate_limit_wait()
        
        url = f"{self.steam_store}/appdetails"
        params = {
            'appids': app_id,
            'cc': 'us',
            'l': 'english'
        }
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(url, params=params)
                
                # Handle rate limiting specifically
                if response.status_code == 429:
                    logger.warning(f"Rate limited on app {app_id}, waiting 60 seconds...")
                    await asyncio.sleep(60)
                    raise Exception("Rate limited, will retry")
                
                response.raise_for_status()
                data = response.json()
                
                app_data = data.get(str(app_id), {})
                if not app_data.get('success', False):
                    return None
                
                return app_data.get('data')
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    logger.warning(f"Rate limited, waiting before retry...")
                    await asyncio.sleep(60)
                raise
            except Exception as e:
                logger.warning(f"Failed to fetch details for app {app_id}: {e}")
                raise
    
    def parse_game_data(self, app_id: int, raw_data: Dict) -> Optional[Dict]:
        """Parse raw Steam API data into our database schema."""
        try:
            # Skip if not a game
            if raw_data.get('type') not in ['game', 'Game']:
                return None
            
            # Extract price information
            price_overview = raw_data.get('price_overview', {})
            is_free = raw_data.get('is_free', False)
            
            price_usd = None
            original_price_usd = None
            discount_percent = 0
            
            if not is_free and price_overview:
                price_usd = price_overview.get('final', 0) / 100.0
                original_price_usd = price_overview.get('initial', 0) / 100.0
                discount_percent = price_overview.get('discount_percent', 0)
            
            # Extract genres and categories
            genres = [g['description'] for g in raw_data.get('genres', [])]
            categories = [c['description'] for c in raw_data.get('categories', [])]
            
            # Platform support
            platforms = raw_data.get('platforms', {})
            
            # Metacritic
            metacritic = raw_data.get('metacritic', {})
            metacritic_score = metacritic.get('score') if metacritic else None
            
            # Recommendations
            recommendations = raw_data.get('recommendations', {}).get('total', 0)
            
            game_data = {
                'id': app_id,
                'name': raw_data.get('name', ''),
                'type': raw_data.get('type', 'game'),
                'is_free': is_free,
                'price_usd': price_usd,
                'original_price_usd': original_price_usd,
                'discount_percent': discount_percent,
                'short_description': raw_data.get('short_description', ''),
                'detailed_description': raw_data.get('detailed_description', ''),
                'header_image': raw_data.get('header_image', ''),
                'genres': genres,
                'categories': categories,
                'tags': [],
                'developers': raw_data.get('developers', []),
                'publishers': raw_data.get('publishers', []),
                'release_date': raw_data.get('release_date', {}).get('date', ''),
                'windows': platforms.get('windows', False),
                'mac': platforms.get('mac', False),
                'linux': platforms.get('linux', False),
                'metacritic_score': metacritic_score,
                'recommendations': recommendations,
                'data_complete': True,
            }
            
            return game_data
        except Exception as e:
            logger.error(f"Error parsing game data for {app_id}: {e}")
            return None
    
    async def collect_popular_games(self, db: Session, max_games: int = 20000):
        """
        Collect data for popular games using SteamSpy as primary source.
        Includes smart rate limiting and progress saving.
        """
        logger.info(f"Starting collection of up to {max_games} games...")
        logger.info("Using conservative rate limiting to avoid 429 errors...")
        
        # Get app list from SteamSpy
        all_apps = await self.get_app_list_from_steamspy(limit=max_games)
        
        if not all_apps:
            logger.error("Could not fetch any games. Please check your internet connection.")
            return 0, 0
        
        logger.info(f"Fetching details for {len(all_apps)} apps...")
        logger.info(f"Estimated time: {len(all_apps) * 1.5 / 60:.1f} minutes (1.5s per game + cooldowns)")
        
        collected = 0
        failed = 0
        batch = []
        consecutive_failures = 0
        
        for i, app in enumerate(all_apps):
            app_id = app['appid']
            
            try:
                # Fetch details from Steam with rate limiting
                details = await self.get_app_details(app_id)
                
                if details:
                    game_data = self.parse_game_data(app_id, details)
                    
                    if game_data:
                        batch.append(game_data)
                        collected += 1
                        consecutive_failures = 0  # Reset on success
                        
                        # Save in batches
                        if len(batch) >= settings.BATCH_SIZE:
                            self._save_batch(db, batch)
                            batch = []
                            logger.info(f"✓ Progress: {collected}/{len(all_apps)} games collected ({failed} failed)")
                    else:
                        failed += 1
                        consecutive_failures += 1
                else:
                    failed += 1
                    consecutive_failures += 1
                    
            except Exception as e:
                logger.error(f"Error processing app {app_id}: {e}")
                failed += 1
                consecutive_failures += 1
                
                # If too many consecutive failures, take longer break
                if consecutive_failures >= 5:
                    logger.warning(f"⚠ {consecutive_failures} consecutive failures, taking extended break...")
                    await asyncio.sleep(120)  # 2 minute break
                    consecutive_failures = 0
            
            # Progress update every 25 games
            if (i + 1) % 25 == 0:
                success_rate = (collected / (i + 1)) * 100 if i > 0 else 0
                logger.info(f"📊 Processed {i + 1}/{len(all_apps)} apps | Success rate: {success_rate:.1f}% | Collected: {collected}")
        
        # Save remaining batch
        if batch:
            self._save_batch(db, batch)
        
        logger.info("=" * 60)
        logger.info(f"✅ Collection complete!")
        logger.info(f"   Collected: {collected} games")
        logger.info(f"   Failed: {failed} games")
        logger.info(f"   Success rate: {(collected/(collected+failed)*100):.1f}%")
        logger.info("=" * 60)
        
        return collected, failed
    
    def _save_batch(self, db: Session, games: List[Dict]):
        """Save a batch of games to the database using upsert"""
        try:
            stmt = insert(Game).values(games)
            stmt = stmt.on_conflict_do_update(
                index_elements=['id'],
                set_={
                    'name': stmt.excluded.name,
                    'price_usd': stmt.excluded.price_usd,
                    'original_price_usd': stmt.excluded.original_price_usd,
                    'discount_percent': stmt.excluded.discount_percent,
                    'short_description': stmt.excluded.short_description,
                    'detailed_description': stmt.excluded.detailed_description,
                    'header_image': stmt.excluded.header_image,
                    'genres': stmt.excluded.genres,
                    'categories': stmt.excluded.categories,
                    'developers': stmt.excluded.developers,
                    'publishers': stmt.excluded.publishers,
                    'recommendations': stmt.excluded.recommendations,
                    'metacritic_score': stmt.excluded.metacritic_score,
                    'data_complete': stmt.excluded.data_complete,
                }
            )
            db.execute(stmt)
            db.commit()
        except Exception as e:
            logger.error(f"Error saving batch: {e}")
            db.rollback()
            raise


# Singleton instance
steam_collector_v2 = SteamCollectorV2()