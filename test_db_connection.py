"""
Test database connection and setup.
Run this after configuring your .env file to verify everything works.
"""

from app.database import engine, SessionLocal
from app.config import settings
from sqlalchemy import text
import sys


def test_connection():
    """Test database connection"""
    print("=" * 60)
    print("Testing Database Connection")
    print("=" * 60)
    print(f"Database URL: {settings.DATABASE_URL[:30]}...")
    print()
    
    try:
        # Test connection
        db = SessionLocal()
        result = db.execute(text("SELECT version()"))
        version = result.scalar()
        
        print("✓ Database connection successful!")
        print(f"✓ PostgreSQL version: {version}")
        
        # Test table creation (only if models exist)
        try:
            from app.database import Base
            from app.models.game import Game
            
            Base.metadata.create_all(bind=engine)
            print("✓ Database tables created successfully!")
        except ImportError:
            print("⚠ Models not created yet - run setup first")
            print("✓ Database connection verified - ready for setup!")
        
        # Check if games table exists
        result = db.execute(text("""
            SELECT COUNT(*) FROM information_schema.tables 
            WHERE table_name = 'games'
        """))
        table_exists = result.scalar()
        
        if table_exists:
            print("✓ Games table exists")
            
            # Count existing games
            result = db.execute(text("SELECT COUNT(*) FROM games"))
            count = result.scalar()
            print(f"✓ Current games in database: {count}")
        
        db.close()
        
        print()
        print("=" * 60)
        print("Setup Status: READY ✓")
        print("=" * 60)
        print()
        print("Next steps:")
        print("1. Run data collection: python scripts/collect_games.py")
        print("2. Start API server: uvicorn app.main:app --reload")
        print()
        
        return 0
        
    except Exception as e:
        print(f"✗ Database connection failed!")
        print(f"Error: {e}")
        print()
        print("Please check:")
        print("1. Your .env file has correct DATABASE_URL")
        print("2. PostgreSQL/Supabase is running and accessible")
        print("3. Database credentials are correct")
        return 1


if __name__ == "__main__":
    sys.exit(test_connection())