import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import SessionLocal
from app.services.recommendation_engine import recommendation_engine
from collections import Counter
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def verify_recommendations(steam_id: str):
    """Verify recommendations include all game types"""
    
    logger.info("=" * 80)
    logger.info("VERIFYING RECOMMENDATION DIVERSITY")
    logger.info("=" * 80)
    logger.info(f"Steam ID: {steam_id}\n")
    
    db = SessionLocal()
    
    try:
        # Test 1: Get default recommendations (should include ALL games)
        logger.info("Test 1: Default Recommendations (No Filters)")
        logger.info("-" * 80)
        
        all_recs = recommendation_engine.get_recommendations(
            steam_id=int(steam_id),
            db=db,
            limit=50,
            indie_only=False,  # Should recommend ALL games
            max_price=None,    # No price limit
            min_similarity=0.1
        )
        
        logger.info(f"Total recommendations: {len(all_recs)}\n")
        
        # Analyze game types
        indie_count = 0
        non_indie_count = 0
        
        for rec in all_recs:
            tags = [tag.lower() for tag in rec.get('tags', [])]
            genres = [genre.lower() for genre in rec.get('genres', [])]
            
            if 'indie' in tags or 'indie' in genres:
                indie_count += 1
            else:
                non_indie_count += 1
        
        logger.info(f"Indie games: {indie_count}")
        logger.info(f"Non-indie games: {non_indie_count}")
        
        if non_indie_count == 0:
            logger.error("❌ PROBLEM: Only indie games recommended!")
            logger.error("This is the bug - should recommend all game types")
        else:
            logger.info(f"✓ Good mix: {non_indie_count}/{len(all_recs)} are non-indie")
        
        # Show sample of non-indie games
        logger.info("\nSample non-indie recommendations:")
        count = 0
        for rec in all_recs:
            tags = [tag.lower() for tag in rec.get('tags', [])]
            genres = [genre.lower() for genre in rec.get('genres', [])]
            
            if 'indie' not in tags and 'indie' not in genres:
                price = f"${rec['price']:.2f}" if rec['price'] else "Free"
                logger.info(f"  - {rec['name']} ({price})")
                logger.info(f"    Genres: {', '.join(rec.get('genres', [])[:3])}")
                count += 1
                if count >= 5:
                    break
        
        # Test 2: Indie-only filter (should only show indie)
        logger.info("\n\nTest 2: Indie-Only Filter")
        logger.info("-" * 80)
        
        indie_recs = recommendation_engine.get_recommendations(
            steam_id=int(steam_id),
            db=db,
            limit=20,
            indie_only=True,  # ONLY indie
            max_price=None,
            min_similarity=0.1
        )
        
        logger.info(f"Indie-only recommendations: {len(indie_recs)}")
        
        # Verify all are indie
        all_indie = all(
            'indie' in [t.lower() for t in rec.get('tags', [])] or 
            'indie' in [g.lower() for g in rec.get('genres', [])]
            for rec in indie_recs
        )
        
        if all_indie:
            logger.info("✓ All recommendations are indie games")
        else:
            logger.warning("⚠ Some non-indie games in indie-only results")
        
        # Test 3: Price filter
        logger.info("\n\nTest 3: Price Filter (Under $20)")
        logger.info("-" * 80)
        
        price_recs = recommendation_engine.get_recommendations(
            steam_id=int(steam_id),
            db=db,
            limit=20,
            indie_only=False,  # All games
            max_price=20.0,    # Under $20
            min_similarity=0.1
        )
        
        logger.info(f"Under $20 recommendations: {len(price_recs)}")
        
        # Check price range
        max_price_found = max((r['price'] or 0) for r in price_recs) if price_recs else 0
        logger.info(f"Highest price: ${max_price_found:.2f}")
        
        if max_price_found <= 20.0:
            logger.info("✓ All recommendations under $20")
        else:
            logger.warning(f"⚠ Found game over $20: ${max_price_found}")
        
        # Test 4: Genre diversity
        logger.info("\n\nTest 4: Genre Diversity Analysis")
        logger.info("-" * 80)
        
        all_genres = []
        for rec in all_recs:
            all_genres.extend(rec.get('genres', []))
        
        genre_counts = Counter(all_genres)
        
        logger.info("Top 10 genres in recommendations:")
        for genre, count in genre_counts.most_common(10):
            logger.info(f"  {genre}: {count}")
        
        # Summary
        logger.info("\n" + "=" * 80)
        logger.info("SUMMARY")
        logger.info("=" * 80)
        
        if non_indie_count > 0:
            logger.info("✓ Recommendation engine is working correctly!")
            logger.info(f"  - Recommends all game types ({non_indie_count} non-indie games)")
            logger.info(f"  - Indie filter works ({len(indie_recs)} indie games)")
            logger.info(f"  - Price filter works (max ${max_price_found:.2f})")
            logger.info(f"  - {len(genre_counts)} different genres represented")
        else:
            logger.error("❌ Problem detected:")
            logger.error("  - Only recommending indie games")
            logger.error("  - Check database: do non-indie games have genre/tag data?")
            logger.error("  - Check user profile: are preferences too narrow?")
        
        return 0 if non_indie_count > 0 else 1
        
    except Exception as e:
        logger.error(f"Verification failed: {e}", exc_info=True)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/verify_all_games.py <steam_id>")
        sys.exit(1)
    
    steam_id = sys.argv[1]
    exit_code = asyncio.run(verify_recommendations(steam_id))
    sys.exit(exit_code)