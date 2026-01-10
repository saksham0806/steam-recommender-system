import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import engine, Base
from app.models.user import User, UserGame, UserWishlist, UserHiddenGame
from app.models.game import Game
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_tables():
    """Create all Phase 2 tables"""
    logger.info("=" * 60)
    logger.info("Creating Phase 2 Database Tables")
    logger.info("=" * 60)
    
    try:
        # Create all tables
        Base.metadata.create_all(bind=engine)
        
        logger.info("✓ Tables created successfully:")
        logger.info("  - users")
        logger.info("  - user_games")
        logger.info("  - user_wishlist")
        logger.info("  - user_hidden_games")
        
        # Verify tables exist
        from sqlalchemy import inspect
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        
        required_tables = ['users', 'user_games', 'user_wishlist', 'user_hidden_games']
        missing_tables = [t for t in required_tables if t not in tables]
        
        if missing_tables:
            logger.error(f"✗ Missing tables: {missing_tables}")
            return 1
        
        logger.info("\n✓ All Phase 2 tables verified!")
        logger.info("=" * 60)
        logger.info("\nNext steps:")
        logger.info("1. Configure STEAM_API_KEY in .env file")
        logger.info("2. Test authentication: curl http://localhost:8000/api/v1/auth/login")
        logger.info("3. Import your library using the auth flow")
        logger.info("=" * 60)
        
        return 0
        
    except Exception as e:
        logger.error(f"✗ Error creating tables: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = create_tables()
    sys.exit(exit_code)