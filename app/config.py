from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    DATABASE_URL: str
    
    STEAM_API_KEY: str = ""
    
    APP_NAME: str = "Steam Game Recommender"
    DEBUG: bool = True
    
    MAX_GAMES_TO_COLLECT: int = 20000
    BATCH_SIZE: int = 100
    REQUEST_DELAY: float = 1.0
    MAX_RETRIES: int = 3
    
    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()