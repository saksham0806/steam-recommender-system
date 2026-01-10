from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ARRAY, Text, Index
from sqlalchemy.sql import func
from app.database import Base


class Game(Base):
    __tablename__ = "games"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(500), nullable=False, index=True)
    type = Column(String(50))
    is_free = Column(Boolean, default=False)
    price_usd = Column(Float, nullable=True)
    original_price_usd = Column(Float, nullable=True)
    discount_percent = Column(Integer, default=0)
    short_description = Column(Text)
    detailed_description = Column(Text)
    header_image = Column(String(500))
    genres = Column(ARRAY(String))
    categories = Column(ARRAY(String))
    tags = Column(ARRAY(String))
    developers = Column(ARRAY(String))
    publishers = Column(ARRAY(String))
    release_date = Column(String(100))
    windows = Column(Boolean, default=False)
    mac = Column(Boolean, default=False)
    linux = Column(Boolean, default=False)
    metacritic_score = Column(Integer, nullable=True)
    recommendations = Column(Integer, default=0)
    data_complete = Column(Boolean, default=False)
    last_updated = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        Index('idx_price_indie', 'price_usd', 'tags'),
        Index('idx_genres', 'genres', postgresql_using='gin'),
        Index('idx_tags', 'tags', postgresql_using='gin'),
        Index('idx_updated', 'last_updated'),
    )
    
    def __repr__(self):
        return f"<Game(id={self.id}, name='{self.name}', price=${self.price_usd})>"
    
    @property
    def is_indie(self):
        if self.tags:
            return 'Indie' in self.tags or 'indie' in [tag.lower() for tag in self.tags]
        if self.genres:
            return 'Indie' in self.genres or 'indie' in [genre.lower() for genre in self.genres]
        return False
