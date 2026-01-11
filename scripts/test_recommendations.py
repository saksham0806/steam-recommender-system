"""
Test the recommendation engine

Usage:
    python scripts/test_recommendations.py <steam_id>
"""

import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import SessionLocal
from app.services.recommendation_engine import recommendation_engine
from app.models.user import User
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_recommendations(steam_id: str):
    """Test recommendation engine"""
    
    logger.info("=" * 80)
    logger.info("RECOMMENDATION ENGINE TEST")
    logger.info("=" * 80)
    logger.info(f"Steam ID: {steam_id}\n")
    
    db = SessionLocal()
    
    try:
        # Check if user exists
        user = db.query(User).filter(User.steam_id == int(steam_id)).first()
        
        if not user:
            logger.error(f"User {steam_id} not found in database")
            logger.info("Run this first: python scripts/test_auth.py {steam_id}")
            return 1
        
        logger.info(f"User: {user.persona_name}")
        logger.info(f"Total games: {user.total_games}")
        logger.info(f"Total playtime: {user.total_playtime / 60:.1f} hours\n")
        
        # Test 1: Build user profile
        logger.info("1. Building User Profile")
        logger.info("-" * 80)
        
        profile = recommendation_engine.build_user_profile(int(steam_id), db)
        
        logger.info(f"Games analyzed: {profile['total_games']}")
        logger.info(f"Owned games: {len(profile['owned_games'])}")
        logger.info(f"Hidden games: {len(profile['hidden_games'])}")
        logger.info(f"Wishlist items: {len(profile['wishlist_games'])}")
        logger.info(f"Avg playtime: {profile['avg_playtime'] / 60:.1f} hours")
        
        logger.info(f"\nTop 5 Genres:")
        for i, genre in enumerate(profile['top_genres'][:5], 1):
            weight = profile['genre_weights'].get(genre, 0)
            logger.info(f"  {i}. {genre} (weight: {weight:.3f})")
        
        logger.info(f"\nTop 5 Tags:")
        for i, tag in enumerate(profile['top_tags'][:5], 1):
            weight = profile['tag_weights'].get(tag, 0)
            logger.info(f"  {i}. {tag} (weight: {weight:.3f})")
        
        # Test 2: Generate recommendations
        logger.info("\n2. Generating Recommendations")
        logger.info("-" * 80)
        
        recommendations = recommendation_engine.get_recommendations(
            steam_id=int(steam_id),
            db=db,
            limit=10,
            indie_only=False,
            max_price=None,
            min_similarity=0.1
        )
        
        logger.info(f"Generated {len(recommendations)} recommendations\n")
        
        if recommendations:
            logger.info("Top 10 Recommendations:")
            logger.info("")
            
            for i, rec in enumerate(recommendations, 1):
                price = f"${rec['price']:.2f}" if rec['price'] else "Free"
                logger.info(f"{i}. {rec['name']}")
                logger.info(f"   Score: {rec['final_score']:.3f} | Similarity: {rec['similarity_score']:.3f}")
                logger.info(f"   Price: {price} | Recommendations: {rec['recommendations']:,}")
                logger.info(f"   Genres: {', '.join(rec['genres'][:3])}")
                
                # Generate explanation
                from app.models.game import Game
                game = db.query(Game).filter(Game.id == rec['game_id']).first()
                if game:
                    explanation = recommendation_engine.explain_recommendation(game, profile)
                    logger.info(f"   Why: {explanation}")
                
                logger.info("")
        else:
            logger.warning("No recommendations generated!")
            logger.info("Possible reasons:")
            logger.info("  - No games in database")
            logger.info("  - User owns all matching games")
            logger.info("  - Filters too restrictive")
        
        # Test 3: Generate indie-only recommendations
        logger.info("\n3. Indie-Only Recommendations (Max $15)")
        logger.info("-" * 80)
        
        indie_recs = recommendation_engine.get_recommendations(
            steam_id=int(steam_id),
            db=db,
            limit=5,
            indie_only=True,
            max_price=15.0,
            min_similarity=0.1
        )
        
        logger.info(f"Found {len(indie_recs)} indie recommendations under $15\n")
        
        for i, rec in enumerate(indie_recs, 1):
            price = f"${rec['price']:.2f}" if rec['price'] else "Free"
            logger.info(f"{i}. {rec['name']} - {price} (score: {rec['final_score']:.3f})")
        
        logger.info("\n" + "=" * 80)
        logger.info("✓ Recommendation Engine Test Complete!")
        logger.info("=" * 80)
        logger.info("\nNext steps:")
        logger.info(f"  - API: curl http://localhost:8000/api/v1/recommendations/{steam_id}")
        logger.info(f"  - Profile: curl http://localhost:8000/api/v1/recommendations/{steam_id}/profile")
        logger.info("  - Docs: http://localhost:8000/docs")
        
        return 0
        
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_recommendations.py <steam_id>")
        sys.exit(1)
    
    steam_id = sys.argv[1]
    exit_code = asyncio.run(test_recommendations(steam_id))
    sys.exit(exit_code)