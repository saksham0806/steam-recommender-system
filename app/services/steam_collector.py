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


class SteamCollector:
    """Service for collecting game data from Steam"""
    
    def __init__(self):
        self.base_url = "https://store.steampowered.com/api"
        self.api_url = "https://api.steampowered.com"
        self.timeout = httpx.Timeout(30.0)
        
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def get_app_list(self) -> List[Dict]:
        """
        Fetch the complete list of Steam apps.
        Returns a list of dicts with 'appid' and 'name'
        """
        # Try multiple endpoints as Steam API can be inconsistent
        endpoints = [
            f"{self.api_url}/ISteamApps/GetAppList/v2/",
            f"{self.api_url}/ISteamApps/GetAppList/v0002/",
        ]
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for url in endpoints:
                try:
                    response = await client.get(url)
                    response.raise_for_status()
                    data = response.json()
                    apps = data.get('applist', {}).get('apps', [])
                    logger.info(f"Retrieved {len(apps)} apps from Steam using {url}")
                    return apps
                except httpx.HTTPStatusError as e:
                    logger.warning(f"Endpoint {url} failed with {e.response.status_code}")
                    continue
                except Exception as e:
                    logger.warning(f"Endpoint {url} failed: {e}")
                    continue
            
            # If all endpoints fail, use alternative method
            logger.warning("All standard endpoints failed, using alternative method...")
            return await self._get_app_list_alternative()
    
    async def _get_app_list_alternative(self) -> List[Dict]:
        """
        Alternative method to get app list by scraping popular/featured games
        and using a curated list of popular app IDs as fallback.
        """
        logger.info("Using alternative app discovery method...")
        
        # Start with a curated list of popular game IDs
        # These are known popular games across different genres
        popular_app_ids = [
            # AAA & Popular
            570, 730, 440, 271590, 1172470, 578080, 892970, 1091500, 
            # Indie hits
            261550, 413150, 367520, 105600, 252490, 236850, 391540, 
            # RPG
            1086940, 377160, 582010, 292030, 435150, 782330,
            # Strategy
            1158310, 289070, 230410, 236390, 255710,
            # Action
            1174180, 774361, 383870, 275850, 1245620,
            # Roguelike
            646570, 1326470, 1145360, 268910, 241600,
            # Simulation
            255710, 892970, 221100, 244850, 975370,
            # Multiplayer
            1966720, 1203220, 1517290, 1426210, 1794680,
        ]
        
        # Also try to get the featured games from store
        try:
            featured_url = "https://store.steampowered.com/api/featured/"
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(featured_url)
                if response.status_code == 200:
                    data = response.json()
                    # Extract app IDs from featured games
                    for category in ['large_capsules', 'featured_win', 'featured_mac', 'featured_linux']:
                        if category in data:
                            for item in data[category]:
                                if 'id' in item:
                                    popular_app_ids.append(item['id'])
        except Exception as e:
            logger.warning(f"Could not fetch featured games: {e}")
        
        # Remove duplicates and convert to app list format
        unique_ids = list(set(popular_app_ids))
        apps = [{'appid': app_id, 'name': f'App_{app_id}'} for app_id in unique_ids]
        
        logger.info(f"Created app list with {len(apps)} popular games")
        return apps
    
    async def _discover_games_from_tags(self) -> List[Dict]:
        """
        Discover games by browsing Steam's tag pages.
        Returns a list of app IDs found through tag browsing.
        """
        logger.info("Discovering games through Steam tags...")
        
        # Popular tags to search
        tags = [
            'indie', 'action', 'adventure', 'rpg', 'strategy', 
            'simulation', 'puzzle', 'platformer', 'roguelike',
            'multiplayer', 'singleplayer', 'horror', 'survival'
        ]
        
        discovered_apps = []
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for tag in tags:
                try:
                    # Use Steam's tag browsing API
                    url = f"https://store.steampowered.com/api/getappsingenre"
                    params = {
                        'genre': tag,
                        'start': 0,
                        'count': 50  # Get top 50 per tag
                    }
                    
                    response = await client.get(url, params=params)
                    if response.status_code == 200:
                        data = response.json()
                        if 'items' in data:
                            for item in data['items']:
                                if 'id' in item:
                                    discovered_apps.append({
                                        'appid': item['id'],
                                        'name': item.get('name', f'Game_{item["id"]}')
                                    })
                    
                    await asyncio.sleep(0.5)  # Rate limiting
                    
                except Exception as e:
                    logger.warning(f"Could not fetch games for tag '{tag}': {e}")
                    continue
        
        logger.info(f"Discovered {len(discovered_apps)} games through tags")
        return discovered_apps
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
    async def get_app_details(self, app_id: int) -> Optional[Dict]:
        """
        Fetch detailed information for a specific app.
        Returns None if the app doesn't exist or data is unavailable.
        """
        url = f"{self.base_url}/appdetails"
        params = {
            'appids': app_id,
            'cc': 'us',  # Country code for USD pricing
            'l': 'english'
        }
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                
                app_data = data.get(str(app_id), {})
                if not app_data.get('success', False):
                    return None
                
                return app_data.get('data')
            except Exception as e:
                logger.warning(f"Failed to fetch details for app {app_id}: {e}")
                return None
    
    def parse_game_data(self, app_id: int, raw_data: Dict) -> Optional[Dict]:
        """
        Parse raw Steam API data into our database schema.
        Returns a dict ready for database insertion.
        """
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
                # Prices are in cents
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
                'tags': [],  # Will be populated separately if needed
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
        Collect data for the most popular games on Steam.
        Uses multiple methods to discover games.
        """
        logger.info(f"Starting collection of up to {max_games} games...")
        
        # Method 1: Try to get full app list
        try:
            all_apps = await self.get_app_list()
        except Exception as e:
            logger.error(f"Could not get app list: {e}")
            all_apps = []
        
        # Method 2: If we have very few apps, supplement with discovery
        if len(all_apps) < 100:
            logger.info("App list too small, using game discovery...")
            discovered_apps = await self._discover_games_from_tags()
            all_apps.extend(discovered_apps)
        
        # Filter out apps with very generic names (likely not real games)
        filtered_apps = [
            app for app in all_apps 
            if app.get('name') and len(app.get('name', '')) > 2
        ]
        
        # Remove duplicates based on appid
        seen = set()
        unique_apps = []
        for app in filtered_apps:
            if app['appid'] not in seen:
                seen.add(app['appid'])
                unique_apps.append(app)
        
        # Limit to max_games
        apps_to_fetch = unique_apps[:max_games]
        logger.info(f"Fetching details for {len(apps_to_fetch)} apps...")
        
        collected = 0
        failed = 0
        batch = []
        
        for i, app in enumerate(apps_to_fetch):
            app_id = app['appid']
            
            # Fetch details
            details = await self.get_app_details(app_id)
            
            if details:
                game_data = self.parse_game_data(app_id, details)
                
                if game_data:
                    batch.append(game_data)
                    collected += 1
                    
                    # Save in batches
                    if len(batch) >= settings.BATCH_SIZE:
                        self._save_batch(db, batch)
                        batch = []
                        logger.info(f"Progress: {collected}/{len(apps_to_fetch)} games collected")
                else:
                    failed += 1
            else:
                failed += 1
            
            # Rate limiting
            if i % 10 == 0:
                await asyncio.sleep(settings.REQUEST_DELAY)
            
            # Progress update
            if (i + 1) % 100 == 0:
                logger.info(f"Processed {i + 1}/{len(apps_to_fetch)} apps")
        
        # Save remaining batch
        if batch:
            self._save_batch(db, batch)
        
        logger.info(f"Collection complete! Collected: {collected}, Failed: {failed}")
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
steam_collector = SteamCollector()