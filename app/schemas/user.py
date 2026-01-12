from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class UserGameBase(BaseModel):
    """Base schema for user's owned game"""
    game_id: int
    playtime_forever: int = 0
    playtime_2weeks: Optional[int] = None


class UserGameCreate(UserGameBase):
    """Schema for adding game to user's library"""
    steam_id: int


class UserGameResponse(BaseModel):
    """Response schema with game details"""
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


class UserWishlistBase(BaseModel):
    """Base schema for wishlist item"""
    game_id: int
    priority: int = 0


class UserWishlistCreate(UserWishlistBase):
    """Schema for adding to wishlist"""
    steam_id: int


class UserWishlistResponse(BaseModel):
    """Response schema with game details"""
    id: int
    game_id: int
    priority: int = 0
    game_name: Optional[str] = None
    game_price: Optional[float] = None
    game_header_image: Optional[str] = None
    added_at: datetime
    
    class Config:
        from_attributes = True


class UserHiddenGameBase(BaseModel):
    """Base schema for hidden game"""
    game_id: int
    reason: Optional[str] = None


class UserHiddenGameCreate(UserHiddenGameBase):
    """Schema for hiding a game"""
    steam_id: int


class UserHiddenGameResponse(UserHiddenGameBase):
    """Response schema"""
    id: int
    hidden_at: datetime
    
    class Config:
        from_attributes = True


class UserBase(BaseModel):
    """Base user schema"""
    steam_id: int
    persona_name: str
    profile_url: Optional[str] = None
    avatar_url: Optional[str] = None


class UserCreate(UserBase):
    """Schema for creating user"""
    real_name: Optional[str] = None
    country_code: Optional[str] = None


class UserUpdate(BaseModel):
    """Schema for updating user"""
    persona_name: Optional[str] = None
    avatar_url: Optional[str] = None
    total_games: Optional[int] = None
    total_playtime: Optional[int] = None


class UserProfile(UserBase):
    """Complete user profile"""
    real_name: Optional[str] = None
    country_code: Optional[str] = None
    total_games: int = 0
    total_playtime: int = 0
    last_login: datetime
    created_at: datetime
    
    class Config:
        from_attributes = True


class UserLibraryStats(BaseModel):
    """Statistics about user's library"""
    steam_id: int
    total_games: int
    total_playtime_hours: float
    most_played_game: Optional[str] = None
    most_played_hours: Optional[float] = None
    recent_games: int = 0
    wishlist_count: int = 0
    hidden_count: int = 0
    top_genres: List[str] = []


class LibrarySyncRequest(BaseModel):
    """Request to sync user's Steam library"""
    steam_id: int
    force_refresh: bool = False


class LibrarySyncResponse(BaseModel):
    """Response from library sync"""
    steam_id: int
    user_name: str
    games_added: int
    games_updated: int
    total_games: int
    wishlist_synced: int
    success: bool
    message: str