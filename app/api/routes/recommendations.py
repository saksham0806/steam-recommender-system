from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app.models.user import User
from app.models.game import Game
from app.services.recommendation_engine import recommendation_engine
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class RecommendationResponse(BaseModel):
    """Response schema for game recommendation"""
    game_id: int
    name: str
    similarity_score: float
    final_score: float
    price: Optional[float]
    is_free: bool
    genres: List[str]
    tags: List[str]
    header_image: Optional[str]
    short_description: Optional[str]
    recommendations: int
    in_wishlist: bool
    explanation: Optional[str] = None


class UserProfileResponse(BaseModel):
    """Response schema for user preference profile"""
    steam_id: int
    top_genres: List[str]
    top_tags: List[str]
    total_games_analyzed: int
    owned_games_count: int
    hidden_games_count: int
    wishlist_count: int
    avg_playtime_hours: float


@router.get("/{steam_id}", response_model=List[RecommendationResponse])
async def get_recommendations(
    steam_id: str,
    limit: int = Query(20, ge=1, le=100, description="Number of recommendations"),
    indie_only: bool = Query(False, description="Only recommend indie games"),
    max_price: Optional[float] = Query(None, ge=0, description="Maximum price in USD"),
    min_similarity: float = Query(0.1, ge=0, le=1, description="Minimum similarity threshold"),
    include_explanation: bool = Query(True, description="Include recommendation explanations"),
    db: Session = Depends(get_db)
):
    """
    Get personalized game recommendations for a user
    
    The recommendation engine uses:
    - Content-based filtering on genres and tags
    - Playtime weighting (games played more = higher preference weight)
    - Wishlist boosting (games similar to wishlist items ranked higher)
    - Automatic filtering of owned and hidden games
    
    Query Parameters:
    - **limit**: Number of recommendations (1-100, default: 20)
    - **indie_only**: Only recommend indie games (default: false)
    - **max_price**: Maximum price in USD (default: no limit)
    - **min_similarity**: Minimum similarity score 0-1 (default: 0.1)
    - **include_explanation**: Include explanation for each recommendation
    """
    # Check if user exists
    user = db.query(User).filter(User.steam_id == int(steam_id)).first()
    
    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found. Please sync your library first."
        )
    
    logger.info(f"Generating {limit} recommendations for {user.persona_name}")
    
    try:
        # Get recommendations
        recommendations = recommendation_engine.get_recommendations(
            steam_id=int(steam_id),
            db=db,
            limit=limit,
            indie_only=indie_only,
            max_price=max_price,
            min_similarity=min_similarity
        )
        
        # Add explanations if requested
        if include_explanation:
            user_profile = recommendation_engine.build_user_profile(int(steam_id), db)
            
            for rec in recommendations:
                game = db.query(Game).filter(Game.id == rec['game_id']).first()
                if game:
                    rec['explanation'] = recommendation_engine.explain_recommendation(
                        game, user_profile
                    )
        
        return [RecommendationResponse(**rec) for rec in recommendations]
        
    except Exception as e:
        logger.error(f"Error generating recommendations: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate recommendations: {str(e)}"
        )


@router.get("/{steam_id}/profile", response_model=UserProfileResponse)
async def get_user_profile(
    steam_id: str,
    db: Session = Depends(get_db)
):
    """
    Get user's preference profile
    
    Shows what genres and tags the recommendation engine identified
    as user preferences based on their play history.
    """
    user = db.query(User).filter(User.steam_id == int(steam_id)).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    try:
        profile = recommendation_engine.build_user_profile(int(steam_id), db)
        
        return UserProfileResponse(
            steam_id=int(steam_id),
            top_genres=profile['top_genres'],
            top_tags=profile['top_tags'],
            total_games_analyzed=profile['total_games'],
            owned_games_count=len(profile['owned_games']),
            hidden_games_count=len(profile['hidden_games']),
            wishlist_count=len(profile['wishlist_games']),
            avg_playtime_hours=profile['avg_playtime'] / 60.0
        )
        
    except Exception as e:
        logger.error(f"Error building user profile: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to build profile: {str(e)}"
        )


@router.get("/{steam_id}/similar/{game_id}")
async def get_similar_games(
    steam_id: str,
    game_id: int,
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """
    Find games similar to a specific game
    
    Useful for "If you like this game, you might also like..." recommendations
    """
    # Check if game exists
    game = db.query(Game).filter(Game.id == game_id).first()
    
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    
    # Build a temporary profile based on this single game
    temp_profile = {
        'top_genres': game.genres or [],
        'top_tags': game.tags or [],
        'genre_weights': {g: 1.0 for g in (game.genres or [])},
        'tag_weights': {t: 1.0 for t in (game.tags or [])},
        'owned_games': set(),
        'hidden_games': set(),
        'wishlist_games': set(),
        'avg_playtime': 0,
        'total_games': 1
    }
    
    # If user specified, exclude their owned/hidden games
    if steam_id:
        user_profile = recommendation_engine.build_user_profile(int(steam_id), db)
        temp_profile['owned_games'] = user_profile['owned_games']
        temp_profile['hidden_games'] = user_profile['hidden_games']
    
    # Find similar games
    candidates = db.query(Game).filter(
        Game.data_complete == True,
        Game.id != game_id,  # Not the same game
        Game.id.notin_(temp_profile['owned_games'])
    ).limit(500).all()
    
    similar_games = []
    for candidate in candidates:
        similarity = recommendation_engine.calculate_similarity(candidate, temp_profile)
        
        if similarity > 0.1:
            similar_games.append({
                'game_id': candidate.id,
                'name': candidate.name,
                'similarity_score': similarity,
                'price': candidate.price_usd,
                'genres': candidate.genres or [],
                'tags': candidate.tags or [],
                'header_image': candidate.header_image
            })
    
    # Sort by similarity
    similar_games.sort(key=lambda x: x['similarity_score'], reverse=True)
    
    return similar_games[:limit]