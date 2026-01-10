from app.database import engine, SessionLocal
from app.config import settings
from sqlalchemy import text
import sys


def test_connection():
    print("=" * 60)
    print("Testing Database Connection")
    print("=" * 60)
    
    try:
        db = SessionLocal()
        result = db.execute(text("SELECT version()"))
        version = result.scalar()
        
        print("✓ Database connection successful!")
        print(f"✓ PostgreSQL version: {version}")
        
        from app.database import Base
        from app.models.game import Game
        
        Base.metadata.create_all(bind=engine)
        print("✓ Database tables created successfully!")
        
        result = db.execute(text("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'games'"))
        table_exists = result.scalar()
        
        if table_exists:
            print("✓ Games table exists")
            result = db.execute(text("SELECT COUNT(*) FROM games"))
            count = result.scalar()
            print(f"✓ Current games in database: {count}")
        
        db.close()
        
        print("\n" + "=" * 60)
        print("Setup Status: READY ✓")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Run: python scripts/collect_games.py --max-games 100")
        print("2. Start server: uvicorn app.main:app --reload")
        
        return 0
        
    except Exception as e:
        print(f"✗ Database connection failed!")
        print(f"Error: {e}")
        print("\nPlease check your .env file")
        return 1


if __name__ == "__main__":
    sys.exit(test_connection())
