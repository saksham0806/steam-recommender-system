from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import List, Optional
from app.database import get_db
from app.models.user import User, UserGame, UserWishlist, UserHiddenGame
from app.models.game import Game
from app.schemas.user import (
    UserProfile,
    UserLibraryStats,
    UserGameResponse,
    UserWishlistResponse,
    UserHiddenGameResponse
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{steam_id}", response_model=UserProfile)
async def get_user_profile(steam_id: str, db: Session = Depends(get_db)):
    """Get user profile"""
    user = db.query(User).filter(User.steam_id == int(steam_id)).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return user


@router.get("/{steam_id}/library", response_model=List[UserGameResponse])
async def get_user_library(
    steam_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    sort_by: str = Query("playtime", enum=["playtime", "recent", "name"]),
    db: Session = Depends(get_db)
):
    """Get user's game library"""
    query = db.query(UserGame, Game).join(
        Game, UserGame.game_id == Game.id
    ).filter(UserGame.steam_id == int(steam_id))
    
    if sort_by == "playtime":
        query = query.order_by(desc(UserGame.playtime_forever))
    elif sort_by == "recent":
        query = query.order_by(desc(UserGame.last_played))
    elif sort_by == "name":
        query = query.order_by(Game.name)
    
    results = query.offset(skip).limit(limit).all()
    
    response = []
    for user_game, game in results:
        response.append({
            'id': user_game.id,
            'game_id': user_game.game_id,
            'playtime_forever': user_game.playtime_forever,
            'playtime_2weeks': user_game.playtime_2weeks,
            'game_name': game.name,
            'game_header_image': game.header_image,
            'last_played': user_game.last_played,
            'added_at': user_game.added_at,
        })
    
    return [UserGameResponse(**item) for item in response]


@router.get("/{steam_id}/wishlist", response_model=List[UserWishlistResponse])
async def get_user_wishlist(
    steam_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """Get user's wishlist"""
    results = db.query(UserWishlist, Game).join(
        Game, UserWishlist.game_id == Game.id
    ).filter(UserWishlist.steam_id == int(steam_id)).offset(skip).limit(limit).all()
    
    response = []
    for wishlist_item, game in results:
        response.append({
            'id': wishlist_item.id,
            'game_id': wishlist_item.game_id,
            'priority': wishlist_item.priority,
            'game_name': game.name,
            'game_price': game.price_usd,
            'game_header_image': game.header_image,
            'added_at': wishlist_item.added_at,
        })
    
    return [UserWishlistResponse(**item) for item in response]


@router.get("/{steam_id}/stats", response_model=UserLibraryStats)
async def get_user_stats(steam_id: str, db: Session = Depends(get_db)):
    """Get detailed statistics about user's library"""
    user = db.query(User).filter(User.steam_id == int(steam_id)).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    most_played = db.query(UserGame, Game).join(
        Game, UserGame.game_id == Game.id
    ).filter(UserGame.steam_id == int(steam_id)).order_by(
        desc(UserGame.playtime_forever)
    ).first()
    
    most_played_game = None
    most_played_hours = None
    if most_played:
        most_played_game = most_played[1].name
        most_played_hours = most_played[0].playtime_forever / 60.0
    
    recent_games = db.query(func.count(UserGame.id)).filter(
        UserGame.steam_id == int(steam_id),
        UserGame.playtime_2weeks.isnot(None),
        UserGame.playtime_2weeks > 0
    ).scalar()
    
    wishlist_count = db.query(func.count(UserWishlist.id)).filter(
        UserWishlist.steam_id == int(steam_id)
    ).scalar()
    
    hidden_count = db.query(func.count(UserHiddenGame.id)).filter(
        UserHiddenGame.steam_id == int(steam_id)
    ).scalar()
    
    top_genres_query = db.query(
        func.unnest(Game.genres).label('genre'),
        func.count().label('count')
    ).join(
        UserGame, Game.id == UserGame.game_id
    ).filter(
        UserGame.steam_id == int(steam_id),
        Game.genres.isnot(None)
    ).group_by('genre').order_by(desc('count')).limit(5)
    
    top_genres = [row[0] for row in top_genres_query.all()]
    
    return UserLibraryStats(
        steam_id=int(steam_id),
        total_games=user.total_games or 0,
        total_playtime_hours=(user.total_playtime or 0) / 60.0,
        most_played_game=most_played_game,
        most_played_hours=most_played_hours,
        recent_games=recent_games or 0,
        wishlist_count=wishlist_count or 0,
        hidden_count=hidden_count or 0,
        top_genres=top_genres
    )


@router.post("/{steam_id}/hidden", response_model=UserHiddenGameResponse)
async def hide_game(
    steam_id: str,
    game_id: int,
    reason: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Mark a game as 'Not Interested'"""
    existing = db.query(UserHiddenGame).filter(
        UserHiddenGame.steam_id == int(steam_id),
        UserHiddenGame.game_id == game_id
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Game already hidden")
    
    hidden_game = UserHiddenGame(
        steam_id=int(steam_id),
        game_id=game_id,
        reason=reason
    )
    db.add(hidden_game)
    db.commit()
    db.refresh(hidden_game)
    
    return hidden_game


@router.delete("/{steam_id}/hidden/{game_id}")
async def unhide_game(steam_id: str, game_id: int, db: Session = Depends(get_db)):
    """Remove game from hidden list"""
    hidden_game = db.query(UserHiddenGame).filter(
        UserHiddenGame.steam_id == int(steam_id),
        UserHiddenGame.game_id == game_id
    ).first()
    
    if not hidden_game:
        raise HTTPException(status_code=404, detail="Hidden game not found")
    
    db.delete(hidden_game)
    db.commit()
    
    return {"success": True, "message": "Game unhidden"}


@router.get("/{steam_id}/hidden", response_model=List[UserHiddenGameResponse])
async def get_hidden_games(steam_id: str, db: Session = Depends(get_db)):
    """Get list of hidden games"""
    hidden_games = db.query(UserHiddenGame).filter(
        UserHiddenGame.steam_id == int(steam_id)
    ).all()
    
    return hidden_games
