from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class UserBase(BaseModel):
    steam_id: int
    persona_name: str
    profile_url: Optional[str] = None
    avatar_url: Optional[str] = None


class UserProfile(UserBase):
    real_name: Optional[str] = None
    country_code: Optional[str] = None
    total_games: int = 0
    total_playtime: int = 0
    last_login: datetime
    created_at: datetime
    
    class Config:
        from_attributes = True


class UserLibraryStats(BaseModel):
    steam_id: int
    total_games: int
    total_playtime_hours: float
    most_played_game: Optional[str] = None
    most_played_hours: Optional[float] = None
    recent_games: int = 0
    wishlist_count: int = 0
    hidden_count: int = 0
    top_genres: List[str] = []


class UserGameResponse(BaseModel):
    id: int
    game_id: int
    playtime_forever: int
    playtime_2weeks: Optional[int] = None
    game_name: Optional[str] = None
    game_header_image: Optional[str] = None
    last_played: Optional[datetime] = None
    added_at: datetime
    
    class Config:
        from_attributes = True


class UserWishlistResponse(BaseModel):
    id: int
    game_id: int
    priority: int = 0
    game_name: Optional[str] = None
    game_price: Optional[float] = None
    game_header_image: Optional[str] = None
    added_at: datetime
    
    class Config:
        from_attributes = True


class UserHiddenGameResponse(BaseModel):
    id: int
    game_id: int
    reason: Optional[str] = None
    hidden_at: datetime
    
    class Config:
        from_attributes = True


class LibrarySyncResponse(BaseModel):
    steam_id: int
    user_name: str
    games_added: int
    games_updated: int
    total_games: int
    wishlist_synced: int
    success: bool
    message: str
