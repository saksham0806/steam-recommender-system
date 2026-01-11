import numpy as np
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from app.models.game import Game
from app.models.user import User, UserGame, UserWishlist, UserHiddenGame
from collections import Counter
import logging

logger = logging.getLogger(__name__)


class RecommendationEngine:
    """
    Content-based recommendation engine using:
    - Genre/tag similarity (cosine similarity)
    - Playtime weighting
    - Wishlist boosting
    - Price filtering
    """
    
    def __init__(self):
        self.genre_weight = 0.6
        self.tag_weight = 0.4
        self.wishlist_boost = 1.5
        self.playtime_threshold = 60  # Minutes (1 hour)
    
    def build_user_profile(self, steam_id: int, db: Session) -> Dict:
        """
        Build user preference profile from their library
        
        Returns:
            {
                'top_genres': [...],
                'top_tags': [...],
                'genre_weights': {...},
                'tag_weights': {...},
                'owned_games': set(),
                'hidden_games': set(),
                'wishlist_games': set(),
                'avg_playtime': float,
                'total_games': int
            }
        """
        logger.info(f"Building profile for user {steam_id}")
        
        # Get user's owned games with playtime
        user_games = db.query(UserGame, Game).join(
            Game, UserGame.game_id == Game.id
        ).filter(
            UserGame.steam_id == steam_id,
            UserGame.playtime_forever >= self.playtime_threshold  # Filter out barely played
        ).all()
        
        if not user_games:
            logger.warning(f"No games with sufficient playtime for user {steam_id}")
            return self._empty_profile(steam_id, db)
        
        # Collect genres and tags weighted by playtime
        genre_counter = Counter()
        tag_counter = Counter()
        total_playtime = 0
        owned_ids = set()
        
        for user_game, game in user_games:
            playtime = user_game.playtime_forever
            total_playtime += playtime
            owned_ids.add(game.id)
            
            # Weight by playtime (more playtime = higher preference)
            weight = np.log1p(playtime)  # log(1 + playtime) to reduce extreme values
            
            if game.genres:
                for genre in game.genres:
                    genre_counter[genre] += weight
            
            if game.tags:
                for tag in game.tags:
                    tag_counter[tag] += weight
        
        # Normalize weights
        total_genre_weight = sum(genre_counter.values()) or 1
        total_tag_weight = sum(tag_counter.values()) or 1
        
        genre_weights = {
            genre: count / total_genre_weight 
            for genre, count in genre_counter.items()
        }
        tag_weights = {
            tag: count / total_tag_weight 
            for tag, count in tag_counter.items()
        }
        
        # Get top preferences
        top_genres = [genre for genre, _ in genre_counter.most_common(10)]
        top_tags = [tag for tag, _ in tag_counter.most_common(15)]
        
        # Get hidden and wishlist games
        hidden_ids = set(
            db.query(UserHiddenGame.game_id)
            .filter(UserHiddenGame.steam_id == steam_id)
            .all()
        )
        hidden_ids = {id[0] for id in hidden_ids}
        
        wishlist_ids = set(
            db.query(UserWishlist.game_id)
            .filter(UserWishlist.steam_id == steam_id)
            .all()
        )
        wishlist_ids = {id[0] for id in wishlist_ids}
        
        profile = {
            'top_genres': top_genres,
            'top_tags': top_tags,
            'genre_weights': genre_weights,
            'tag_weights': tag_weights,
            'owned_games': owned_ids,
            'hidden_games': hidden_ids,
            'wishlist_games': wishlist_ids,
            'avg_playtime': total_playtime / len(user_games),
            'total_games': len(user_games)
        }
        
        logger.info(f"Profile built: {len(top_genres)} genres, {len(top_tags)} tags, "
                   f"{len(owned_ids)} owned, {len(hidden_ids)} hidden")
        
        return profile
    
    def _empty_profile(self, steam_id: int, db: Session) -> Dict:
        """Return empty profile for users with no playtime data"""
        owned_ids = set(
            db.query(UserGame.game_id)
            .filter(UserGame.steam_id == steam_id)
            .all()
        )
        owned_ids = {id[0] for id in owned_ids}
        
        hidden_ids = set(
            db.query(UserHiddenGame.game_id)
            .filter(UserHiddenGame.steam_id == steam_id)
            .all()
        )
        hidden_ids = {id[0] for id in hidden_ids}
        
        return {
            'top_genres': [],
            'top_tags': [],
            'genre_weights': {},
            'tag_weights': {},
            'owned_games': owned_ids,
            'hidden_games': hidden_ids,
            'wishlist_games': set(),
            'avg_playtime': 0,
            'total_games': 0
        }
    
    def calculate_similarity(
        self, 
        game: Game, 
        user_profile: Dict
    ) -> float:
        """
        Calculate similarity score between a game and user profile
        Uses weighted cosine similarity on genres and tags
        
        Returns:
            Similarity score (0-1)
        """
        if not user_profile['genre_weights'] and not user_profile['tag_weights']:
            return 0.0
        
        genre_score = 0.0
        tag_score = 0.0
        
        # Calculate genre similarity
        if game.genres and user_profile['genre_weights']:
            genre_matches = 0
            for genre in game.genres:
                if genre in user_profile['genre_weights']:
                    genre_matches += user_profile['genre_weights'][genre]
            
            # Normalize by number of genres in game
            genre_score = genre_matches / len(game.genres) if game.genres else 0
        
        # Calculate tag similarity
        if game.tags and user_profile['tag_weights']:
            tag_matches = 0
            for tag in game.tags:
                if tag in user_profile['tag_weights']:
                    tag_matches += user_profile['tag_weights'][tag]
            
            # Normalize by number of tags in game
            tag_score = tag_matches / len(game.tags) if game.tags else 0
        
        # Weighted combination
        similarity = (
            self.genre_weight * genre_score + 
            self.tag_weight * tag_score
        )
        
        return min(similarity, 1.0)  # Cap at 1.0
    
    def get_recommendations(
        self,
        steam_id: int,
        db: Session,
        limit: int = 50,
        indie_only: bool = False,
        max_price: Optional[float] = None,
        min_similarity: float = 0.1
    ) -> List[Dict]:
        """
        Generate personalized game recommendations
        
        Args:
            steam_id: User's Steam ID
            db: Database session
            limit: Number of recommendations to return
            indie_only: Only recommend indie games (default: False - all games)
            max_price: Maximum price filter (default: None - all prices)
            min_similarity: Minimum similarity threshold
            
        Returns:
            List of recommended games with scores
        """
        logger.info(f"Generating recommendations for user {steam_id}")
        logger.info(f"Filters: indie_only={indie_only}, max_price={max_price}")
        
        # Build user profile
        profile = self.build_user_profile(steam_id, db)
        
        if not profile['genre_weights'] and not profile['tag_weights']:
            logger.warning("Empty user profile - using popular games fallback")
            return self._fallback_recommendations(db, limit, indie_only, max_price)
        
        # Build candidate query - START WITH ALL GAMES
        query = db.query(Game).filter(
            Game.data_complete == True,
            Game.id.notin_(profile['owned_games']),  # Not owned
            Game.id.notin_(profile['hidden_games'])  # Not hidden
        )
        
        # ONLY apply indie filter if explicitly requested
        if indie_only:
            logger.info("Applying indie filter")
            query = query.filter(
                or_(
                    func.array_to_string(Game.tags, ',').ilike('%indie%'),
                    func.array_to_string(Game.genres, ',').ilike('%indie%')
                )
            )
        
        # ONLY apply price filter if specified
        if max_price is not None:
            logger.info(f"Applying price filter: max ${max_price}")
            query = query.filter(
                or_(
                    Game.is_free == True,
                    and_(
                        Game.price_usd.isnot(None),
                        Game.price_usd <= max_price
                    )
                )
            )
        
        # Get candidates (limit to 2000 for performance, increased from 1000)
        candidates = query.limit(2000).all()
        
        logger.info(f"Evaluating {len(candidates)} candidate games")
        
        if not candidates:
            logger.warning("No candidates found after filtering!")
            logger.info("This might mean:")
            logger.info("  - User owns all games in database")
            logger.info("  - Filters too restrictive")
            logger.info("  - Need to collect more games (Phase 1)")
            return []
        
        # Calculate similarity scores
        recommendations = []
        for game in candidates:
            similarity = self.calculate_similarity(game, profile)
            
            # Skip low similarity games
            if similarity < min_similarity:
                continue
            
            # Boost if similar to wishlist items
            boost = 1.0
            if game.id in profile['wishlist_games']:
                boost = self.wishlist_boost
            
            # Boost popular games slightly
            popularity_boost = 1.0
            if game.recommendations and game.recommendations > 1000:
                popularity_boost = 1.1
            
            final_score = similarity * boost * popularity_boost
            
            recommendations.append({
                'game_id': game.id,
                'name': game.name,
                'similarity_score': similarity,
                'final_score': final_score,
                'price': game.price_usd,
                'is_free': game.is_free,
                'genres': game.genres or [],
                'tags': game.tags or [],
                'header_image': game.header_image,
                'short_description': game.short_description,
                'recommendations': game.recommendations or 0,
                'in_wishlist': game.id in profile['wishlist_games']
            })
        
        # Sort by final score
        recommendations.sort(key=lambda x: x['final_score'], reverse=True)
        
        # Return top N
        top_recommendations = recommendations[:limit]
        
        logger.info(f"Returning {len(top_recommendations)} recommendations")
        
        if top_recommendations:
            avg_score = sum(r['similarity_score'] for r in top_recommendations) / len(top_recommendations)
            logger.info(f"Average similarity score: {avg_score:.3f}")
        
        return top_recommendations
    
    def _fallback_recommendations(
        self,
        db: Session,
        limit: int,
        indie_only: bool,
        max_price: Optional[float]
    ) -> List[Dict]:
        """
        Fallback to popular games when user has no profile
        Returns all games by default unless filters specified
        """
        logger.info("Using fallback recommendations (popular games)")
        logger.info(f"Filters: indie_only={indie_only}, max_price={max_price}")
        
        query = db.query(Game).filter(Game.data_complete == True)
        
        # ONLY filter if explicitly requested
        if indie_only:
            logger.info("Applying indie filter in fallback")
            query = query.filter(
                or_(
                    func.array_to_string(Game.tags, ',').ilike('%indie%'),
                    func.array_to_string(Game.genres, ',').ilike('%indie%')
                )
            )
        
        if max_price is not None:
            logger.info(f"Applying price filter in fallback: max ${max_price}")
            query = query.filter(
                or_(
                    Game.is_free == True,
                    and_(
                        Game.price_usd.isnot(None),
                        Game.price_usd <= max_price
                    )
                )
            )
        
        # Order by popularity (games with most recommendations)
        popular_games = query.order_by(
            Game.recommendations.desc().nullslast()
        ).limit(limit).all()
        
        logger.info(f"Fallback returning {len(popular_games)} popular games")
        
        return [
            {
                'game_id': game.id,
                'name': game.name,
                'similarity_score': 0.0,
                'final_score': 0.0,
                'price': game.price_usd,
                'is_free': game.is_free,
                'genres': game.genres or [],
                'tags': game.tags or [],
                'header_image': game.header_image,
                'short_description': game.short_description,
                'recommendations': game.recommendations or 0,
                'in_wishlist': False
            }
            for game in popular_games
        ]
    
    def explain_recommendation(
        self,
        game: Game,
        user_profile: Dict
    ) -> str:
        """
        Generate human-readable explanation for why game was recommended
        """
        reasons = []
        
        # Check genre matches
        if game.genres and user_profile['top_genres']:
            matching_genres = [
                g for g in game.genres 
                if g in user_profile['top_genres'][:5]
            ]
            if matching_genres:
                reasons.append(f"Similar genres: {', '.join(matching_genres)}")
        
        # Check tag matches
        if game.tags and user_profile['top_tags']:
            matching_tags = [
                t for t in game.tags 
                if t in user_profile['top_tags'][:5]
            ]
            if matching_tags:
                reasons.append(f"Matching tags: {', '.join(matching_tags)}")
        
        # Check if in wishlist
        if game.id in user_profile.get('wishlist_games', set()):
            reasons.append("Already in your wishlist")
        
        # Check popularity
        if game.recommendations and game.recommendations > 5000:
            reasons.append(f"Highly rated ({game.recommendations:,} recommendations)")
        
        if not reasons:
            reasons.append("Popular game in this category")
        
        return " | ".join(reasons)


# Singleton instance
recommendation_engine = RecommendationEngine()