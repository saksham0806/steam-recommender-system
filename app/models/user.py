from sqlalchemy import Column, String, BigInteger, Integer, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class User(Base):
    __tablename__ = "users"
    
    steam_id = Column(BigInteger, primary_key=True, index=True)
    persona_name = Column(String(255))
    profile_url = Column(String(500))
    avatar_url = Column(String(500))
    real_name = Column(String(255), nullable=True)
    country_code = Column(String(10), nullable=True)
    profile_visibility = Column(Integer, default=3)
    last_login = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    total_games = Column(Integer, default=0)
    total_playtime = Column(Integer, default=0)
    
    owned_games = relationship("UserGame", back_populates="user", cascade="all, delete-orphan")
    wishlist = relationship("UserWishlist", back_populates="user", cascade="all, delete-orphan")
    hidden_games = relationship("UserHiddenGame", back_populates="user", cascade="all, delete-orphan")


class UserGame(Base):
    __tablename__ = "user_games"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    steam_id = Column(BigInteger, ForeignKey('users.steam_id', ondelete='CASCADE'), nullable=False)
    game_id = Column(Integer, ForeignKey('games.id'), nullable=False)
    playtime_forever = Column(Integer, default=0)
    playtime_2weeks = Column(Integer, default=0, nullable=True)
    last_played = Column(DateTime(timezone=True), nullable=True)
    added_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    user = relationship("User", back_populates="owned_games")
    game = relationship("Game")
    
    __table_args__ = (
        Index('idx_user_games_steam_id', 'steam_id'),
        Index('idx_user_games_game_id', 'game_id'),
        Index('idx_user_games_playtime', 'playtime_forever'),
        Index('idx_user_games_composite', 'steam_id', 'game_id', unique=True),
    )


class UserWishlist(Base):
    __tablename__ = "user_wishlist"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    steam_id = Column(BigInteger, ForeignKey('users.steam_id', ondelete='CASCADE'), nullable=False)
    game_id = Column(Integer, ForeignKey('games.id'), nullable=False)
    priority = Column(Integer, default=0)
    added_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="wishlist")
    game = relationship("Game")
    
    __table_args__ = (
        Index('idx_wishlist_steam_id', 'steam_id'),
        Index('idx_wishlist_game_id', 'game_id'),
        Index('idx_wishlist_composite', 'steam_id', 'game_id', unique=True),
    )


class UserHiddenGame(Base):
    __tablename__ = "user_hidden_games"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    steam_id = Column(BigInteger, ForeignKey('users.steam_id', ondelete='CASCADE'), nullable=False)
    game_id = Column(Integer, ForeignKey('games.id'), nullable=False)
    reason = Column(String(50), nullable=True)
    hidden_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="hidden_games")
    game = relationship("Game")
    
    __table_args__ = (
        Index('idx_hidden_steam_id', 'steam_id'),
        Index('idx_hidden_game_id', 'game_id'),
        Index('idx_hidden_composite', 'steam_id', 'game_id', unique=True),
    )
