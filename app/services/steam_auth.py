import httpx
import re
from typing import Optional, Dict
from urllib.parse import urlencode, parse_qs, urlparse
from app.config import settings
import logging

logger = logging.getLogger(__name__)


class SteamAuth:
    """
    Steam OpenID 2.0 Authentication Service
    Handles Steam login flow without requiring user passwords
    """
    
    def __init__(self):
        self.openid_url = "https://steamcommunity.com/openid/login"
        self.steam_api_url = "https://api.steampowered.com"
        
    def get_login_url(self, return_url: str) -> str:
        """
        Generate Steam OpenID login URL
        
        Args:
            return_url: URL where Steam will redirect after login
            
        Returns:
            Steam login URL for user to visit
        """
        params = {
            'openid.ns': 'http://specs.openid.net/auth/2.0',
            'openid.mode': 'checkid_setup',
            'openid.return_to': return_url,
            'openid.realm': return_url.split('/callback')[0],  # Base URL
            'openid.identity': 'http://specs.openid.net/auth/2.0/identifier_select',
            'openid.claimed_id': 'http://specs.openid.net/auth/2.0/identifier_select',
        }
        
        login_url = f"{self.openid_url}?{urlencode(params)}"
        logger.info(f"Generated Steam login URL")
        return login_url
    
    async def verify_authentication(self, callback_params: Dict[str, str]) -> Optional[str]:
        """
        Verify Steam OpenID response and extract Steam ID
        
        Args:
            callback_params: Query parameters from Steam's callback
            
        Returns:
            Steam ID (as string) if valid, None otherwise
        """
        try:
            # Change mode to check_authentication
            validation_params = dict(callback_params)
            validation_params['openid.mode'] = 'check_authentication'
            
            # Verify with Steam
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.openid_url,
                    data=validation_params
                )
                
                # Check if validation successful
                if 'is_valid:true' in response.text:
                    # Extract Steam ID from claimed_id
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
        """
        Get player profile information from Steam API
        
        Args:
            steam_id: Steam 64-bit ID
            
        Returns:
            Player data dict or None
        """
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
        """
        Get user's owned games from Steam API
        
        Args:
            steam_id: Steam 64-bit ID
            
        Returns:
            Dict with 'game_count' and 'games' list
        """
        if not settings.STEAM_API_KEY:
            logger.error("STEAM_API_KEY required to fetch owned games")
            return None
        
        url = f"{self.steam_api_url}/IPlayerService/GetOwnedGames/v1/"
        params = {
            'key': settings.STEAM_API_KEY,
            'steamid': steam_id,
            'include_appinfo': 1,  # Include game names
            'include_played_free_games': 1,  # Include F2P games
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
        """
        Get user's wishlist by scraping Steam store
        Note: Steam doesn't provide wishlist via API, requires web scraping
        
        Args:
            steam_id: Steam 64-bit ID
            
        Returns:
            List of game IDs or empty list if private/not found, None on error
        """
        # Steam wishlist URLs - try multiple formats
        # The profile URL format is more reliable than the direct ID format
        urls = [
            # Try with login check disabled (public access)
            f"https://store.steampowered.com/wishlist/profiles/{steam_id}/wishlistdata/?p=0",
            # Alternative format
            f"https://store.steampowered.com/wishlist/id/{steam_id}/wishlistdata/",
        ]
        
        for url in urls:
            try:
                logger.info(f"Attempting to fetch wishlist from: {url}")
                
                # Important: Don't follow redirects automatically
                # A redirect means the wishlist is private or invalid
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(30.0),
                    follow_redirects=False  # Don't auto-follow redirects
                ) as client:
                    response = await client.get(url)
                    
                    # Check for redirects (wishlist is private)
                    if response.status_code in [301, 302, 303, 307, 308]:
                        logger.warning(f"Wishlist redirected (likely private) for Steam ID: {steam_id}")
                        logger.warning(f"Redirect to: {response.headers.get('location', 'unknown')}")
                        # Try next URL format
                        continue
                    
                    # Wishlist is private or doesn't exist
                    if response.status_code == 403:
                        logger.warning(f"Wishlist is private (403) for Steam ID: {steam_id}")
                        return []
                    
                    if response.status_code == 404:
                        logger.warning(f"Wishlist not found (404) at {url}")
                        continue
                    
                    if response.status_code != 200:
                        logger.warning(f"Unexpected status {response.status_code} from {url}")
                        continue
                    
                    # Check if we got actual JSON data
                    content_type = response.headers.get('content-type', '')
                    if 'json' not in content_type:
                        logger.warning(f"Response is not JSON (got {content_type})")
                        continue
                    
                    # Try to parse response
                    try:
                        data = response.json()
                        
                        # Check if empty response
                        if not data or data == {} or data == []:
                            logger.info(f"Wishlist is empty for Steam ID: {steam_id}")
                            return []
                        
                        # Extract game IDs
                        wishlist_ids = []
                        for app_id in data.keys():
                            try:
                                wishlist_ids.append(int(app_id))
                            except (ValueError, TypeError):
                                logger.warning(f"Invalid app ID in wishlist: {app_id}")
                                continue
                        
                        if wishlist_ids:
                            logger.info(f"Successfully retrieved {len(wishlist_ids)} wishlist items")
                            return wishlist_ids
                        else:
                            logger.warning("Wishlist data present but no valid IDs found")
                            return []
                            
                    except ValueError as e:
                        logger.error(f"Failed to parse JSON from {url}: {e}")
                        logger.debug(f"Response text (first 500 chars): {response.text[:500]}")
                        continue
                    
            except httpx.TimeoutException:
                logger.error(f"Timeout fetching wishlist from {url}")
                continue
            except Exception as e:
                logger.error(f"Error fetching wishlist from {url}: {e}")
                continue
        
        # If all URLs failed, wishlist is likely private
        logger.error(f"Failed to fetch wishlist from all sources for Steam ID: {steam_id}")
        logger.error("Most likely cause: Wishlist privacy is set to 'Private' or 'Friends Only'")
        return []  # Return empty list instead of None to indicate privacy issue


# Singleton instance
steam_auth = SteamAuth()