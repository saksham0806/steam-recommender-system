from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class GameBase(BaseModel):
    """Base game schema with common fields"""
    name: str
    type: Optional[str] = None
    is_free: bool = False
    price_usd: Optional[float] = None
    original_price_usd: Optional[float] = None
    discount_percent: int = 0
    short_description: Optional[str] = None
    header_image: Optional[str] = None
    genres: Optional[List[str]] = []
    categories: Optional[List[str]] = []
    tags: Optional[List[str]] = []
    developers: Optional[List[str]] = []
    publishers: Optional[List[str]] = []
    release_date: Optional[str] = None
    windows: bool = False
    mac: bool = False
    linux: bool = False


class GameCreate(GameBase):
    """Schema for creating a new game"""
    id: int  # Steam App ID


class GameUpdate(BaseModel):
    """Schema for updating game data"""
    price_usd: Optional[float] = None
    original_price_usd: Optional[float] = None
    discount_percent: Optional[int] = None
    tags: Optional[List[str]] = None
    recommendations: Optional[int] = None
    data_complete: Optional[bool] = None


class GameInDB(GameBase):
    """Schema for game as stored in database"""
    id: int
    detailed_description: Optional[str] = None
    metacritic_score: Optional[int] = None
    recommendations: int = 0
    data_complete: bool = False
    last_updated: datetime
    created_at: datetime
    
    class Config:
        from_attributes = True


class GameResponse(BaseModel):
    """Schema for API responses"""
    id: int
    name: str
    price_usd: Optional[float] = None
    discount_percent: int = 0
    short_description: Optional[str] = None
    header_image: Optional[str] = None
    genres: Optional[List[str]] = []
    tags: Optional[List[str]] = []
    is_indie: bool = False
    
    class Config:
        from_attributes = True


class CollectionStats(BaseModel):
    """Statistics about the game collection"""
    total_games: int
    indie_games: int
    free_games: int
    paid_games: int
    average_price: float
    last_updated: Optional[datetime] = None