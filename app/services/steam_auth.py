import httpx
import re
from typing import Optional, Dict
from urllib.parse import urlencode
from app.config import settings
import logging

logger = logging.getLogger(__name__)


class SteamAuth:
    """Steam OpenID 2.0 Authentication Service"""
    
    def __init__(self):
        self.openid_url = "https://steamcommunity.com/openid/login"
        self.steam_api_url = "https://api.steampowered.com"
        
    def get_login_url(self, return_url: str) -> str:
        """Generate Steam OpenID login URL"""
        params = {
            'openid.ns': 'http://specs.openid.net/auth/2.0',
            'openid.mode': 'checkid_setup',
            'openid.return_to': return_url,
            'openid.realm': return_url.split('/callback')[0],
            'openid.identity': 'http://specs.openid.net/auth/2.0/identifier_select',
            'openid.claimed_id': 'http://specs.openid.net/auth/2.0/identifier_select',
        }
        
        login_url = f"{self.openid_url}?{urlencode(params)}"
        logger.info(f"Generated Steam login URL")
        return login_url
    
    async def verify_authentication(self, callback_params: Dict[str, str]) -> Optional[str]:
        """Verify Steam OpenID response and extract Steam ID"""
        try:
            validation_params = dict(callback_params)
            validation_params['openid.mode'] = 'check_authentication'
            
            async with httpx.AsyncClient() as client:
                response = await client.post(self.openid_url, data=validation_params)
                
                if 'is_valid:true' in response.text:
                    claimed_id = callback_params.get('openid.claimed_id', '')
                    steam_id_match = re.search(r'(\d+)$', claimed_id)
                    
                    if steam_id_match:
                        steam_id = steam_id_match.group(1)
                        logger.info(f"Successfully authenticated Steam ID: {steam_id}")
                        return steam_id
                    else:
                        logger.error("Could not extract Steam ID from claimed_id")
                        return None
                else:
                    logger.error("Steam OpenID verification failed")
                    return None
                    
        except Exception as e:
            logger.error(f"Error verifying Steam authentication: {e}")
            return None
    
    async def get_player_summaries(self, steam_id: str) -> Optional[Dict]:
        """Get player profile information from Steam API"""
        if not settings.STEAM_API_KEY:
            logger.warning("STEAM_API_KEY not configured, skipping profile fetch")
            return None
        
        url = f"{self.steam_api_url}/ISteamUser/GetPlayerSummaries/v2/"
        params = {
            'key': settings.STEAM_API_KEY,
            'steamids': steam_id
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                
                players = data.get('response', {}).get('players', [])
                if players:
                    return players[0]
                else:
                    logger.error(f"No player data found for Steam ID: {steam_id}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error fetching player summaries: {e}")
            return None
    
    async def get_owned_games(self, steam_id: str) -> Optional[Dict]:
        """Get user's owned games from Steam API"""
        if not settings.STEAM_API_KEY:
            logger.error("STEAM_API_KEY required to fetch owned games")
            return None
        
        url = f"{self.steam_api_url}/IPlayerService/GetOwnedGames/v1/"
        params = {
            'key': settings.STEAM_API_KEY,
            'steamid': steam_id,
            'include_appinfo': 1,
            'include_played_free_games': 1,
        }
        
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                
                result = data.get('response', {})
                game_count = result.get('game_count', 0)
                logger.info(f"Retrieved {game_count} games for Steam ID: {steam_id}")
                
                return result
                
        except Exception as e:
            logger.error(f"Error fetching owned games: {e}")
            return None
    
    async def get_wishlist(self, steam_id: str) -> Optional[list]:
        """Get user's wishlist by scraping Steam store"""
        url = f"https://store.steampowered.com/wishlist/profiles/{steam_id}/wishlistdata/"
        
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
                response = await client.get(url)
                
                if response.status_code == 403 or response.status_code == 404:
                    logger.warning(f"Wishlist is private or not found for Steam ID: {steam_id}")
                    return []
                
                response.raise_for_status()
                data = response.json()
                
                wishlist_ids = [int(app_id) for app_id in data.keys()]
                logger.info(f"Retrieved {len(wishlist_ids)} wishlist items for Steam ID: {steam_id}")
                
                return wishlist_ids
                
        except Exception as e:
            logger.error(f"Error fetching wishlist: {e}")
            return None


steam_auth = SteamAuth()