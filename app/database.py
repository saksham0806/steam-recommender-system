from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Import settings - will handle if config.py doesn't exist yet
try:
    from app.config import settings
    DATABASE_URL = settings.DATABASE_URL
    DEBUG = settings.DEBUG
except (ImportError, AttributeError):
    import os
    from dotenv import load_dotenv
    load_dotenv()
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/steam_recommender")
    DEBUG = os.getenv("DEBUG", "True").lower() == "true"

# Create database engine
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # Verify connections before using them
    echo=DEBUG,  # Log SQL queries in debug mode
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


def get_db():
    """
    Dependency function to get database session.
    Use with FastAPI's Depends() for automatic cleanup.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database tables"""
    Base.metadata.create_all(bind=engine)