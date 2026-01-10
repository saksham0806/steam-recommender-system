from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class GameBase(BaseModel):
    name: str
    type: Optional[str] = None
    is_free: bool = False
    price_usd: Optional[float] = None
    genres: Optional[List[str]] = []
    tags: Optional[List[str]] = []


class GameResponse(BaseModel):
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
    total_games: int
    indie_games: int
    free_games: int
    paid_games: int
    average_price: float
    last_updated: Optional[datetime] = None
