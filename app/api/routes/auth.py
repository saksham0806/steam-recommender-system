from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.steam_auth import steam_auth
from app.services.library_sync import library_sync_service
from app.schemas.user import LibrarySyncResponse
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/login")
async def steam_login(request: Request):
    """Initiate Steam OpenID login flow"""
    base_url = str(request.base_url).rstrip('/')
    callback_url = f"{base_url}/api/v1/auth/callback"
    
    login_url = steam_auth.get_login_url(callback_url)
    
    return {
        "login_url": login_url,
        "message": "Redirect user to this URL to authenticate with Steam"
    }


@router.get("/callback")
async def steam_callback(request: Request, db: Session = Depends(get_db)):
    """Handle Steam OpenID callback"""
    params = dict(request.query_params)
    
    steam_id = await steam_auth.verify_authentication(params)
    
    if not steam_id:
        raise HTTPException(status_code=401, detail="Steam authentication failed")
    
    user = await library_sync_service.sync_user_profile(steam_id, db)
    
    return JSONResponse({
        "success": True,
        "steam_id": str(steam_id),
        "user_name": user.persona_name,
        "message": "Successfully authenticated with Steam!",
        "next_step": f"Call /api/v1/auth/sync/{steam_id} to import your library"
    })


@router.get("/logout")
async def logout():
    """Logout user"""
    return {"success": True, "message": "Logged out successfully"}


@router.post("/sync/{steam_id}", response_model=LibrarySyncResponse)
async def sync_library(steam_id: str, db: Session = Depends(get_db)):
    """Sync user's Steam library"""
    try:
        result = await library_sync_service.full_sync(steam_id, db)
        return LibrarySyncResponse(**result)
    except Exception as e:
        logger.error(f"Library sync failed for {steam_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Library sync failed: {str(e)}")


@router.get("/status/{steam_id}")
async def get_auth_status(steam_id: str, db: Session = Depends(get_db)):
    """Check if user is authenticated and library is synced"""
    from app.models.user import User, UserGame
    
    user = db.query(User).filter(User.steam_id == int(steam_id)).first()
    
    if not user:
        return {
            "authenticated": False,
            "library_synced": False,
            "message": "User not found. Please login with Steam."
        }
    
    games_count = db.query(UserGame).filter(UserGame.steam_id == int(steam_id)).count()
    
    return {
        "authenticated": True,
        "library_synced": games_count > 0,
        "user_name": user.persona_name,
        "total_games": user.total_games,
        "games_in_db": games_count,
        "last_login": user.last_login.isoformat()
    }