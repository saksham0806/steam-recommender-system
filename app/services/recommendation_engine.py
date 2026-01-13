import numpy as np
from typing import List, Dict, Optional, Set, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, desc, text
from app.models.game import Game
from app.models.user import User, UserGame, UserWishlist, UserHiddenGame
from collections import Counter, defaultdict
import logging

logger = logging.getLogger(__name__)

class RecommendationEngine:
    
    def __init__(self):
        # Adjusted weights for better discrimination
        self.genre_weight = 0.35
        self.tag_weight = 0.45
        self.category_weight = 0.20
        self.wishlist_boost = 2.0
        self.playtime_threshold = 60
        self.min_playtime_fallback = 10
        
        # Diversity parameters
        self.diversity_factor = 0.15
    
    def build_user_profile(self, steam_id: int, db: Session) -> Dict:
        """Build enhanced user profile with TF-IDF-like weighting"""
        logger.info(f"Building profile for user {steam_id}")
        
        # Fetch user games with playtime threshold
        user_games = db.query(UserGame, Game).join(
            Game, UserGame.game_id == Game.id
        ).filter(
            UserGame.steam_id == steam_id,
            UserGame.playtime_forever >= self.playtime_threshold
        ).order_by(UserGame.playtime_forever.desc()).all()
        
        # Fallback to lower threshold
        if not user_games:
            logger.info(f"Using fallback threshold for {steam_id}")
            user_games = db.query(UserGame, Game).join(
                Game, UserGame.game_id == Game.id
            ).filter(
                UserGame.steam_id == steam_id,
                UserGame.playtime_forever >= self.min_playtime_fallback
            ).order_by(UserGame.playtime_forever.desc()).all()

        if not user_games:
            logger.warning(f"No games found for user {steam_id}")
            return self._empty_profile(steam_id, db)
        
        # Calculate global item frequencies for TF-IDF weighting
        total_games_in_db = db.query(func.count(Game.id)).filter(Game.data_complete == True).scalar() or 1
        
        # Count how many games each genre/tag/category appears in
        genre_doc_freq = self._get_item_frequencies(db, 'genres')
        tag_doc_freq = self._get_item_frequencies(db, 'tags')
        category_doc_freq = self._get_item_frequencies(db, 'categories')
        
        total_games = len(user_games)
        top_tier_count = max(1, int(total_games * 0.20))
        mid_tier_count = max(2, int(total_games * 0.40))
        
        genre_scores = defaultdict(float)
        tag_scores = defaultdict(float)
        category_scores = defaultdict(float)
        total_playtime = 0
        owned_ids = set()
        
        for i, (user_game, game) in enumerate(user_games):
            playtime = user_game.playtime_forever
            total_playtime += playtime
            owned_ids.add(game.id)
            
            # Tier-based importance
            if i < top_tier_count:
                importance = 5.0
            elif i < top_tier_count + mid_tier_count:
                importance = 2.5
            else:
                importance = 1.0
            
            # Logarithmic playtime weight
            playtime_weight = np.log1p(playtime) / 10.0
            base_weight = playtime_weight * importance
            
            # Apply TF-IDF-like weighting for genres
            if game.genres:
                for genre in game.genres:
                    # IDF component: rare genres get higher weight
                    idf = np.log(total_games_in_db / (genre_doc_freq.get(genre, 1) + 1))
                    genre_scores[genre] += base_weight * (1 + idf * 0.5)
            
            # Apply TF-IDF-like weighting for tags
            if game.tags:
                for tag in game.tags:
                    idf = np.log(total_games_in_db / (tag_doc_freq.get(tag, 1) + 1))
                    tag_scores[tag] += base_weight * (1 + idf * 0.5)
            
            # Categories without IDF
            if game.categories:
                for category in game.categories:
                    category_scores[category] += base_weight
        
        # Normalize scores
        def normalize_scores(scores_dict):
            total = sum(scores_dict.values()) or 1
            return {k: v / total for k, v in scores_dict.items()}
        
        genre_weights = normalize_scores(genre_scores)
        tag_weights = normalize_scores(tag_scores)
        category_weights = normalize_scores(category_scores)
        
        # Get top items
        top_genres = [g for g, _ in sorted(genre_scores.items(), key=lambda x: x[1], reverse=True)[:10]]
        top_tags = [t for t, _ in sorted(tag_scores.items(), key=lambda x: x[1], reverse=True)[:25]]
        top_categories = [c for c, _ in sorted(category_scores.items(), key=lambda x: x[1], reverse=True)[:10]]
        
        # Fetch user metadata
        hidden_ids = {id[0] for id in db.query(UserHiddenGame.game_id)
                      .filter(UserHiddenGame.steam_id == steam_id).all()}
        
        wishlist_ids = {id[0] for id in db.query(UserWishlist.game_id)
                        .filter(UserWishlist.steam_id == steam_id).all()}
        
        return {
            'top_genres': top_genres,
            'top_tags': top_tags,
            'top_categories': top_categories,
            'genre_weights': genre_weights,
            'tag_weights': tag_weights,
            'category_weights': category_weights,
            'owned_games': owned_ids,
            'hidden_games': hidden_ids,
            'wishlist_games': wishlist_ids,
            'top_played_games': [g.id for _, g in user_games[:10]],
            'avg_playtime': total_playtime / (total_games or 1),
            'total_games': total_games
        }

    def _get_item_frequencies(self, db: Session, column_name: str) -> Dict[str, int]:
        """Count how many games each item appears in (for IDF calculation)"""
        try:
            # Use unnest to expand arrays and count occurrences
            query = text(f"""
                SELECT item, COUNT(*) as freq
                FROM (
                    SELECT unnest({column_name}) as item
                    FROM games
                    WHERE data_complete = true AND {column_name} IS NOT NULL
                ) subq
                GROUP BY item
            """)
            result = db.execute(query).fetchall()
            return {row[0]: row[1] for row in result}
        except Exception as e:
            logger.warning(f"Could not calculate frequencies for {column_name}: {e}")
            return {}

    def _empty_profile(self, steam_id: int, db: Session) -> Dict:
        """Safe empty profile structure"""
        return {
            'top_genres': [], 'top_tags': [], 'top_categories': [],
            'genre_weights': {}, 'tag_weights': {}, 'category_weights': {},
            'owned_games': set(), 'hidden_games': set(), 'wishlist_games': set(),
            'top_played_games': [], 'avg_playtime': 0, 'total_games': 0
        }
    
    def calculate_similarity(self, game: Game, user_profile: Dict) -> float:
        """
        Enhanced similarity calculation - sum matching weights instead of averaging
        """
        if not user_profile['genre_weights']:
            return 0.0
        
        genre_score = 0.0
        tag_score = 0.0
        category_score = 0.0
        
        # Genre matching - sum of all matching weights
        if game.genres:
            matched_weights = [user_profile['genre_weights'].get(g, 0) for g in game.genres]
            if matched_weights:
                # Sum instead of average to reward multiple matches
                genre_score = sum(matched_weights)
        
        # Tag matching - sum of top matching weights
        if game.tags:
            matched_weights = [user_profile['tag_weights'].get(t, 0) for t in game.tags]
            if matched_weights:
                # Take top 10 tag matches to avoid overwhelming signal
                top_tag_matches = sorted(matched_weights, reverse=True)[:10]
                tag_score = sum(top_tag_matches)
        
        # Category matching
        if game.categories:
            matched_weights = [user_profile['category_weights'].get(c, 0) for c in game.categories]
            if matched_weights:
                category_score = sum(matched_weights)
        
        # Weighted combination
        total_score = (
            genre_score * self.genre_weight +
            tag_score * self.tag_weight +
            category_score * self.category_weight
        )
        
        return total_score

    def get_recommendations(
        self,
        steam_id: int,
        db: Session,
        limit: int = 50,
        indie_only: bool = False,
        max_price: Optional[float] = None,
        min_similarity: float = 0.02
    ) -> List[Dict]:
        """
        Generate personalized recommendations with proper candidate selection
        """
        profile = self.build_user_profile(steam_id, db)
        
        if not profile['genre_weights']:
            logger.warning("Empty profile - using fallback")
            return self._fallback_recommendations(db, limit, indie_only, max_price)
        
        # Build base query
        base_query = db.query(Game).filter(
            Game.data_complete == True,
            Game.id.notin_(profile['owned_games']),
            Game.id.notin_(profile['hidden_games'])
        )
        
        # Apply filters
        if indie_only:
            base_query = base_query.filter(
                or_(
                    func.array_to_string(Game.tags, ',').ilike('%indie%'),
                    func.array_to_string(Game.genres, ',').ilike('%indie%')
                )
            )
        
        if max_price is not None:
            base_query = base_query.filter(
                or_(
                    Game.is_free == True,
                    and_(Game.price_usd.isnot(None), Game.price_usd <= max_price)
                )
            )
        
        # Smart candidate selection using better filtering
        candidates = []
        
        # Strategy 1: Get games matching top genres
        if profile['top_genres']:
            # Build OR conditions for top genres
            genre_conditions = [
                func.array_to_string(Game.genres, ',').ilike(f'%{genre}%')
                for genre in profile['top_genres'][:5]
            ]
            
            genre_candidates = base_query.filter(
                or_(*genre_conditions)
            ).order_by(Game.recommendations.desc().nullslast()).limit(1200).all()
            
            candidates.extend(genre_candidates)
            logger.info(f"Found {len(genre_candidates)} genre-matched candidates")
        
        # Strategy 2: Get games matching top tags
        if profile['top_tags'] and len(candidates) < 1000:
            existing_ids = {c.id for c in candidates}
            
            # Build OR conditions for top tags
            tag_conditions = [
                func.array_to_string(Game.tags, ',').ilike(f'%{tag}%')
                for tag in profile['top_tags'][:10]
            ]
            
            tag_candidates = base_query.filter(
                Game.id.notin_(existing_ids),
                or_(*tag_conditions)
            ).order_by(Game.recommendations.desc().nullslast()).limit(800).all()
            
            candidates.extend(tag_candidates)
            logger.info(f"Added {len(tag_candidates)} tag-matched candidates")
        
        # Strategy 3: Popular backfill if still low
        if len(candidates) < 800:
            existing_ids = {c.id for c in candidates}
            backfill = base_query.filter(
                Game.id.notin_(existing_ids)
            ).order_by(Game.recommendations.desc().nullslast()).limit(500).all()
            candidates.extend(backfill)
            logger.info(f"Added {len(backfill)} popular backfill candidates")
        
        logger.info(f"Scoring {len(candidates)} total candidates")
        
        # Score all candidates
        scored_games = []
        for game in candidates:
            similarity = self.calculate_similarity(game, profile)
            
            if similarity < min_similarity:
                continue
            
            # Apply boosts
            boost = 1.0
            
            # Wishlist boost
            if game.id in profile['wishlist_games']:
                boost *= self.wishlist_boost
            
            # Quality boost (logarithmic popularity)
            if game.recommendations and game.recommendations > 100:
                popularity_boost = 1 + (np.log10(game.recommendations) * 0.08)
                boost *= popularity_boost
            
            final_score = similarity * boost
            
            scored_games.append((game, final_score, similarity))
        
        # Sort by final score
        scored_games.sort(key=lambda x: x[1], reverse=True)
        
        # Apply diversity penalty to avoid recommending too many similar games
        final_results = []
        genre_counts = defaultdict(int)
        tag_counts = defaultdict(int)
        
        for game, f_score, sim_score in scored_games:
            # Calculate diversity penalty
            diversity_penalty = 1.0
            
            for genre in (game.genres or []):
                if genre_counts[genre] > 0:
                    diversity_penalty *= (1 - self.diversity_factor * min(genre_counts[genre], 3))
            
            for tag in (game.tags or [])[:5]:  # Only penalize top tags
                if tag_counts[tag] > 1:
                    diversity_penalty *= (1 - self.diversity_factor * 0.5 * min(tag_counts[tag], 2))
            
            adjusted_score = f_score * diversity_penalty
            
            final_results.append((game, adjusted_score, sim_score, f_score))
            
            # Update counts
            for genre in (game.genres or []):
                genre_counts[genre] += 1
            for tag in (game.tags or [])[:5]:
                tag_counts[tag] += 1
            
            if len(final_results) >= limit * 2:  # Get extra for final sort
                break
        
        # Re-sort after diversity adjustment
        final_results.sort(key=lambda x: x[1], reverse=True)
        
        # Format output
        results = []
        for game, adjusted_score, sim_score, original_score in final_results[:limit]:
            results.append({
                'game_id': game.id,
                'name': game.name,
                'similarity_score': sim_score,
                'final_score': original_score,
                'price': game.price_usd,
                'is_free': game.is_free,
                'genres': game.genres or [],
                'tags': game.tags or [],
                'header_image': game.header_image,
                'short_description': game.short_description,
                'recommendations': game.recommendations,
                'in_wishlist': game.id in profile['wishlist_games'],
                'explanation': self.explain_recommendation(game, profile)
            })
        
        return results

    def _fallback_recommendations(self, db: Session, limit: int, 
                                   indie_only: bool, max_price: Optional[float]) -> List[Dict]:
        """Fallback to popular games"""
        query = db.query(Game).filter(Game.data_complete == True)
        
        if indie_only:
            query = query.filter(
                or_(
                    func.array_to_string(Game.tags, ',').ilike('%indie%'),
                    func.array_to_string(Game.genres, ',').ilike('%indie%')
                )
            )
        
        if max_price is not None:
            query = query.filter(
                or_(Game.is_free == True, 
                    and_(Game.price_usd.isnot(None), Game.price_usd <= max_price))
            )
        
        games = query.order_by(Game.recommendations.desc().nullslast()).limit(limit).all()
        
        return [{
            'game_id': g.id,
            'name': g.name,
            'similarity_score': 0,
            'final_score': 0,
            'price': g.price_usd,
            'is_free': g.is_free,
            'genres': g.genres or [],
            'tags': g.tags or [],
            'header_image': g.header_image,
            'short_description': g.short_description,
            'recommendations': g.recommendations,
            'in_wishlist': False,
            'explanation': "Popular on Steam"
        } for g in games]

    def explain_recommendation(self, game: Game, user_profile: Dict) -> str:
        """Generate explanation for recommendation"""
        if game.id in user_profile['wishlist_games']:
            return "On your Wishlist"
        
        reasons = []
        
        # Find best matching genres
        common_genres = set(game.genres or []) & set(user_profile['top_genres'][:5])
        if common_genres:
            best_genre = max(common_genres, key=lambda g: user_profile['genre_weights'].get(g, 0))
            reasons.append(f"Matches your {best_genre} preference")
        
        # Find best matching tags
        common_tags = set(game.tags or []) & set(user_profile['top_tags'][:15])
        if common_tags and len(reasons) < 2:
            best_tags = sorted(common_tags, 
                             key=lambda t: user_profile['tag_weights'].get(t, 0), 
                             reverse=True)[:2]
            reasons.append(f"Features: {', '.join(best_tags)}")
        
        return " • ".join(reasons) if reasons else "Highly rated"

recommendation_engine = RecommendationEngine()