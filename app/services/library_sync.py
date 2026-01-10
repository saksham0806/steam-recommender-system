from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from app.models.user import User, UserGame, UserWishlist
from app.models.game import Game
from app.services.steam_auth import steam_auth
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class LibrarySyncService:
    """Service for synchronizing user's Steam library with database"""
    
    async def sync_user_profile(self, steam_id: str, db: Session) -> User:
        """Sync user profile information from Steam"""
        player_data = await steam_auth.get_player_summaries(steam_id)
        
        if not player_data:
            user_data = {
                'steam_id': int(steam_id),
                'persona_name': f'User_{steam_id[:8]}',
                'profile_url': f'https://steamcommunity.com/profiles/{steam_id}',
            }
        else:
            user_data = {
                'steam_id': int(steam_id),
                'persona_name': player_data.get('personaname', ''),
                'profile_url': player_data.get('profileurl', ''),
                'avatar_url': player_data.get('avatarfull', ''),
                'real_name': player_data.get('realname'),
                'country_code': player_data.get('loccountrycode'),
                'profile_visibility': player_data.get('communityvisibilitystate', 3),
            }
        
        stmt = insert(User).values(**user_data)
        stmt = stmt.on_conflict_do_update(
            index_elements=['steam_id'],
            set_={
                'persona_name': stmt.excluded.persona_name,
                'profile_url': stmt.excluded.profile_url,
                'avatar_url': stmt.excluded.avatar_url,
                'real_name': stmt.excluded.real_name,
                'country_code': stmt.excluded.country_code,
                'profile_visibility': stmt.excluded.profile_visibility,
                'last_login': datetime.utcnow(),
            }
        )
        db.execute(stmt)
        db.commit()
        
        user = db.query(User).filter(User.steam_id == int(steam_id)).first()
        logger.info(f"Synced profile for user: {user.persona_name}")
        
        return user
    
    async def sync_owned_games(self, steam_id: str, db: Session) -> dict:
        """Sync user's owned games from Steam"""
        games_data = await steam_auth.get_owned_games(steam_id)
        
        if not games_data:
            return {'games_added': 0, 'games_updated': 0, 'error': 'Could not fetch games'}
        
        steam_games = games_data.get('games', [])
        games_added = 0
        games_updated = 0
        
        for game in steam_games:
            app_id = game.get('appid')
            playtime_forever = game.get('playtime_forever', 0)
            playtime_2weeks = game.get('playtime_2weeks')
            
            game_exists = db.query(Game).filter(Game.id == app_id).first()
            
            if not game_exists:
                game_data = {
                    'id': app_id,
                    'name': game.get('name', f'Game_{app_id}'),
                    'header_image': f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/header.jpg",
                    'data_complete': False,
                }
                db.add(Game(**game_data))
                db.flush()
            
            user_game_data = {
                'steam_id': int(steam_id),
                'game_id': app_id,
                'playtime_forever': playtime_forever,
                'playtime_2weeks': playtime_2weeks,
            }
            
            stmt = insert(UserGame).values(**user_game_data)
            stmt = stmt.on_conflict_do_update(
                index_elements=['steam_id', 'game_id'],
                set_={
                    'playtime_forever': stmt.excluded.playtime_forever,
                    'playtime_2weeks': stmt.excluded.playtime_2weeks,
                    'updated_at': datetime.utcnow(),
                }
            )
            result = db.execute(stmt)
            
            if result.rowcount == 1:
                games_added += 1
            else:
                games_updated += 1
        
        total_playtime = sum(g.get('playtime_forever', 0) for g in steam_games)
        user = db.query(User).filter(User.steam_id == int(steam_id)).first()
        if user:
            user.total_games = len(steam_games)
            user.total_playtime = total_playtime
        
        db.commit()
        logger.info(f"Synced {len(steam_games)} games for Steam ID: {steam_id}")
        
        return {
            'games_added': games_added,
            'games_updated': games_updated,
            'total_games': len(steam_games),
        }
    
    async def sync_wishlist(self, steam_id: str, db: Session) -> dict:
        """Sync user's wishlist from Steam"""
        wishlist_ids = await steam_auth.get_wishlist(steam_id)
        
        if wishlist_ids is None:
            return {'wishlist_synced': 0, 'error': 'Could not fetch wishlist'}
        
        if not wishlist_ids:
            return {'wishlist_synced': 0, 'message': 'Wishlist is empty or private'}
        
        db.query(UserWishlist).filter(UserWishlist.steam_id == int(steam_id)).delete()
        wishlist_synced = 0
        
        for app_id in wishlist_ids:
            game_exists = db.query(Game).filter(Game.id == app_id).first()
            
            if not game_exists:
                game_data = {
                    'id': app_id,
                    'name': f'Game_{app_id}',
                    'header_image': f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/header.jpg",
                    'data_complete': False,
                }
                db.add(Game(**game_data))
                db.flush()
            
            wishlist_item = UserWishlist(
                steam_id=int(steam_id),
                game_id=app_id,
                priority=0
            )
            db.add(wishlist_item)
            wishlist_synced += 1
        
        db.commit()
        logger.info(f"Synced {wishlist_synced} wishlist items for Steam ID: {steam_id}")
        
        return {'wishlist_synced': wishlist_synced}
    
    async def full_sync(self, steam_id: str, db: Session) -> dict:
        """Perform full sync: profile, games, and wishlist"""
        logger.info(f"Starting full sync for Steam ID: {steam_id}")
        
        user = await self.sync_user_profile(steam_id, db)
        games_result = await self.sync_owned_games(steam_id, db)
        wishlist_result = await self.sync_wishlist(steam_id, db)
        
        result = {
            'steam_id': int(steam_id),
            'user_name': user.persona_name,
            'games_added': games_result.get('games_added', 0),
            'games_updated': games_result.get('games_updated', 0),
            'total_games': games_result.get('total_games', 0),
            'wishlist_synced': wishlist_result.get('wishlist_synced', 0),
            'success': True,
            'message': 'Library sync completed successfully'
        }
        
        logger.info(f"Full sync completed for {user.persona_name}")
        return result


library_sync_service = LibrarySyncService()