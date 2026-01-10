from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from typing import List, Optional
from app.database import get_db
from app.models.game import Game
from app.schemas.game import GameResponse, CollectionStats

router = APIRouter()


@router.get("/games", response_model=List[GameResponse])
async def get_games(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    indie_only: bool = Query(False),
    max_price: Optional[float] = Query(None, ge=0),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    query = db.query(Game).filter(Game.data_complete == True)
    
    if indie_only:
        query = query.filter(
            func.array_to_string(Game.tags, ',').ilike('%indie%') |
            func.array_to_string(Game.genres, ',').ilike('%indie%')
        )
    
    if max_price is not None:
        query = query.filter(and_(Game.price_usd.isnot(None), Game.price_usd <= max_price))
    
    if search:
        query = query.filter(Game.name.ilike(f"%{search}%"))
    
    query = query.order_by(Game.recommendations.desc())
    games = query.offset(skip).limit(limit).all()
    
    response = []
    for game in games:
        game_dict = {
            'id': game.id,
            'name': game.name,
            'price_usd': game.price_usd,
            'discount_percent': game.discount_percent,
            'short_description': game.short_description,
            'header_image': game.header_image,
            'genres': game.genres or [],
            'tags': game.tags or [],
            'is_indie': game.is_indie
        }
        response.append(GameResponse(**game_dict))
    
    return response


@router.get("/stats", response_model=CollectionStats)
async def get_collection_stats(db: Session = Depends(get_db)):
    total = db.query(func.count(Game.id)).filter(Game.data_complete == True).scalar()
    free_games = db.query(func.count(Game.id)).filter(and_(Game.data_complete == True, Game.is_free == True)).scalar()
    paid_games = db.query(func.count(Game.id)).filter(and_(Game.data_complete == True, Game.is_free == False, Game.price_usd.isnot(None))).scalar()
    indie_games = db.query(func.count(Game.id)).filter(and_(Game.data_complete == True, func.array_to_string(Game.tags, ',').ilike('%indie%') | func.array_to_string(Game.genres, ',').ilike('%indie%'))).scalar()
    avg_price = db.query(func.avg(Game.price_usd)).filter(and_(Game.data_complete == True, Game.price_usd.isnot(None), Game.is_free == False)).scalar()
    last_updated = db.query(func.max(Game.last_updated)).scalar()
    
    return CollectionStats(
        total_games=total or 0,
        indie_games=indie_games or 0,
        free_games=free_games or 0,
        paid_games=paid_games or 0,
        average_price=float(avg_price) if avg_price else 0.0,
        last_updated=last_updated
    )
