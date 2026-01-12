from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Database
    DATABASE_URL: str
    
    # Steam API
    STEAM_API_KEY: str = ""
    
    # Application
    APP_NAME: str = "Steam Game Recommender"
    DEBUG: bool = True
    
    # Data Collection Settings
    MAX_GAMES_TO_COLLECT: int = 20000
    BATCH_SIZE: int = 75  # Reduced from 100 for safer saves
    REQUEST_DELAY: float = 1.5  # Increased to avoid rate limits
    MAX_RETRIES: int = 5  # More retries for resilience
    
    # Rate Limiting (to avoid 429 errors)
    REQUESTS_PER_MINUTE: int = 40  # Conservative: ~40 requests/min
    COOLDOWN_AFTER_N_REQUESTS: int = 50  # Cooldown every 50 requests
    COOLDOWN_DURATION: int = 10  # 10 second cooldown
    EXTENDED_COOLDOWN_AFTER: int = 150  # Extended cooldown every 150 requests
    EXTENDED_COOLDOWN_DURATION: int = 30  # 30 second extended cooldown
    
    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance"""
    return Settings()


settings = get_settings()