from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import engine, Base
from app.api.routes import games, auth, users, recommendations

# Create database tables
Base.metadata.create_all(bind=engine)

# Initialize FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    description="Backend API for Steam Game Recommendations with ML-based Personalization",
    version="3.0.0",
    debug=settings.DEBUG,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(games.router, prefix="/api/v1", tags=["games"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["authentication"])
app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
app.include_router(recommendations.router, prefix="/api/v1/recommendations", tags=["recommendations"])


@app.get("/")
async def root():
    """Root endpoint - API health check"""
    return {
        "message": "Steam Game Recommender API",
        "status": "running",
        "version": "3.0.0",
        "features": [
            "Steam OpenID Authentication",
            "Library Import & Sync",
            "ML-Based Recommendations",
            "Content-Based Filtering",
            "Wishlist Management",
            "Personalized Game Discovery"
        ]
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )