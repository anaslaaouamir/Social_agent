"""Hashtag intelligence router."""
from fastapi import APIRouter, Depends
from models.domain import User
from api.auth_utils import get_current_user
from modules.hashtag_intelligence import HashtagIntelligenceSystem

router = APIRouter()
_system = HashtagIntelligenceSystem()


@router.post("/recommend")
async def recommend_hashtags(payload: dict, current_user: User = Depends(get_current_user)):
    """Get AI-powered hashtag recommendations (Module 3)."""
    rec = await _system.recommend(
        caption=payload.get("caption", ""),
        platform=payload.get("platform", "instagram"),
        category=payload.get("category", "lifestyle"),
        brand_hashtags=payload.get("brand_hashtags", []),
        languages=payload.get("languages", ["fr"]),
        n_hashtags=int(payload.get("n_hashtags", 25)),
    )
    return _system.to_dict(rec)


@router.get("/trending")
async def get_trending(platform: str = "instagram", current_user: User = Depends(get_current_user)):
    """Get currently trending hashtags for Moroccan market."""
    await _system.initialize()
    trending = await _system._get_trending(platform, n=20)
    return [{"tag": m.tag, "score": m.trending_score, "reach": m.avg_reach} for m in trending]
