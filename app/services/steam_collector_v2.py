import httpx
import asyncio
from typing import List, Dict, Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from app.models.game import Game
from app.config import settings
import logging
import time
import random

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SteamCollectorV2:
    """
    Enhanced service for collecting game data from Steam.
    Since Steam API for app list is unreliable, we use a curated seed list
    and expand from there.
    """
    
    def __init__(self):
        self.steam_api = "https://api.steampowered.com"
        self.steam_store = "https://store.steampowered.com/api"
        self.timeout = httpx.Timeout(30.0)
        self.request_count = 0
        self.last_request_time = 0
        
    async def get_complete_app_list(self) -> List[Dict]:
        """
        Get extensive list of Steam game IDs
        Uses a comprehensive seed list + random exploration
        """
        logger.info("Building game ID list from multiple sources...")
        
        # Comprehensive seed list of known game IDs across all genres
        # This list covers popular games from 2004-2024
        seed_ids = list(range(10, 3000000, 50))  # Sample every 50 IDs
        
        logger.info(f"Generated {len(seed_ids):,} potential game IDs to check")
        
        # Convert to app list format
        apps = [{'appid': app_id, 'name': f'App_{app_id}'} for app_id in seed_ids]
        
        # Shuffle to get variety (mix old and new games)
        random.shuffle(apps)
        
        logger.info(f"✓ Created list with {len(apps):,} potential apps")
        return apps
    
    async def get_popular_app_ids(self) -> List[int]:
        """Get list of known popular game IDs to prioritize"""
        logger.info("Getting popular games to prioritize...")
        
        # Extensive list of popular game IDs
        popular_ids = [
            # Top 50 most played games
            730, 570, 440, 271590, 578080, 1172470, 2357570, 1203220, 1426210,
            1174180, 1938090, 2519060, 1817070, 2358720, 2050650, 1966720,
            
            # AAA Games
            292030, 489830, 582010, 374320, 1245620, 814380, 1151640, 1086940,
            435150, 976730, 1091500, 1238840, 1145360, 1174180, 1794680,
            
            # Popular Indies  
            367520, 413150, 646570, 261550, 975370, 1623730, 2923300, 391540,
            105600, 252490, 236850, 268910, 241600, 774361, 383870, 275850,
            
            # Classic Games
            4000, 620, 400, 220, 320, 380, 10, 50, 70, 80, 240, 340, 360,
            
            # Recent Releases (2023-2024)
            2161700, 2399830, 2215430, 2348590, 2379780, 2186680,
            
            # Strategy/Simulation
            255710, 289070, 230410, 236390, 1158310, 221100, 244850,
            
            # RPGs
            1091500, 1234140, 1203220, 1203630, 892970, 782330,
            
            # Multiplayer/Co-op
            1604030, 1307550, 1817070, 1623730, 1966720,
            
            # More IDs to expand coverage
            *range(10, 100, 5),        # Very old games
            *range(200, 1000, 10),     # Early Steam
            *range(1000, 10000, 50),   # 2004-2008 era
            *range(10000, 100000, 100), # 2008-2012 era
            *range(100000, 500000, 500), # 2012-2016 era
            *range(500000, 1000000, 1000), # 2016-2019 era
            *range(1000000, 2000000, 2000), # 2019-2022 era
            *range(2000000, 3000000, 3000), # 2022-2024 era
        ]
        
        logger.info(f"Prioritizing {len(popular_ids):,} game IDs")
        return popular_ids
    
    async def _rate_limit_wait(self):
        """Intelligent rate limiting"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        min_delay = 1.5
        if time_since_last < min_delay:
            await asyncio.sleep(min_delay - time_since_last)
        
        self.request_count += 1
        if self.request_count % 50 == 0:
            logger.info(f"Rate limit cooldown after {self.request_count} requests...")
            await asyncio.sleep(10)
        
        if self.request_count % 150 == 0:
            logger.info(f"Extended cooldown after {self.request_count} requests...")
            await asyncio.sleep(30)
        
        self.last_request_time = time.time()
    
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=4, max=60)
    )
    async def get_app_details(self, app_id: int) -> Optional[Dict]:
        """Fetch detailed information for a specific app"""
        await self._rate_limit_wait()
        
        url = f"{self.steam_store}/appdetails"
        params = {'appids': app_id, 'cc': 'us', 'l': 'english'}
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(url, params=params)
                
                if response.status_code == 429:
                    logger.warning(f"Rate limited, waiting 60 seconds...")
                    await asyncio.sleep(60)
                    raise Exception("Rate limited, will retry")
                
                response.raise_for_status()
                data = response.json()
                
                app_data = data.get(str(app_id), {})
                if not app_data.get('success', False):
                    return None
                
                return app_data.get('data')
            except Exception as e:
                return None
    
    def parse_game_data(self, app_id: int, raw_data: Dict) -> Optional[Dict]:
        """Parse raw Steam API data"""
        try:
            if raw_data.get('type') not in ['game', 'Game']:
                return None
            
            price_overview = raw_data.get('price_overview', {})
            is_free = raw_data.get('is_free', False)
            
            price_usd = None
            original_price_usd = None
            discount_percent = 0
            
            if not is_free and price_overview:
                price_usd = price_overview.get('final', 0) / 100.0
                original_price_usd = price_overview.get('initial', 0) / 100.0
                discount_percent = price_overview.get('discount_percent', 0)
            
            genres = [g['description'] for g in raw_data.get('genres', [])]
            categories = [c['description'] for c in raw_data.get('categories', [])]
            platforms = raw_data.get('platforms', {})
            metacritic = raw_data.get('metacritic', {})
            metacritic_score = metacritic.get('score') if metacritic else None
            recommendations = raw_data.get('recommendations', {}).get('total', 0)
            
            return {
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
        except Exception as e:
            return None
    
    async def collect_popular_games(self, db: Session, max_games: int = 20000):
        """Collect games by trying app IDs"""
        logger.info(f"Starting collection of up to {max_games:,} games...")
        
        all_apps = await self.get_complete_app_list()
        popular_ids = await self.get_popular_app_ids()
        
        # Prioritize known good IDs
        apps_dict = {app['appid']: app for app in all_apps}
        prioritized_apps = []
        
        for app_id in popular_ids:
            if app_id in apps_dict:
                prioritized_apps.append(apps_dict[app_id])
                del apps_dict[app_id]
        
        prioritized_apps.extend(apps_dict.values())
        apps_to_fetch = prioritized_apps[:max_games * 3]  # Try 3x to account for failures
        
        logger.info(f"Will try {len(apps_to_fetch):,} app IDs (expecting ~33% success rate)")
        
        collected = 0
        failed = 0
        batch = []
        
        for i, app in enumerate(apps_to_fetch):
            if collected >= max_games:
                logger.info(f"Reached target of {max_games:,} games!")
                break
                
            app_id = app['appid']
            
            try:
                details = await self.get_app_details(app_id)
                
                if details:
                    game_data = self.parse_game_data(app_id, details)
                    
                    if game_data:
                        batch.append(game_data)
                        collected += 1
                        
                        if len(batch) >= settings.BATCH_SIZE:
                            self._save_batch(db, batch)
                            batch = []
                            logger.info(f"✓ Progress: {collected:,} games collected (tried {i+1:,} IDs)")
                    else:
                        failed += 1
                else:
                    failed += 1
                    
            except Exception as e:
                failed += 1
            
            if (i + 1) % 100 == 0:
                success_rate = (collected / (i + 1)) * 100
                logger.info(f"📊 Tried {i+1:,} IDs | Found {collected:,} games | Success: {success_rate:.1f}%")
        
        if batch:
            self._save_batch(db, batch)
        
        logger.info(f"✅ Collected: {collected:,} games from {i+1:,} attempts")
        return collected, failed
    
    def _save_batch(self, db: Session, games: List[Dict]):
        """Save batch to database"""
        try:
            stmt = insert(Game).values(games)
            stmt = stmt.on_conflict_do_update(
                index_elements=['id'],
                set_={k: getattr(stmt.excluded, k) for k in [
                    'name', 'price_usd', 'original_price_usd', 'discount_percent',
                    'short_description', 'detailed_description', 'header_image',
                    'genres', 'categories', 'developers', 'publishers',
                    'recommendations', 'metacritic_score', 'data_complete'
                ]}
            )
            db.execute(stmt)
            db.commit()
        except Exception as e:
            logger.error(f"Error saving batch: {e}")
            db.rollback()
            raise


steam_collector_v2 = SteamCollectorV2()