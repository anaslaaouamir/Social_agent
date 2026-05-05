"""Timing predictor router."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth_utils import get_current_user
from core.database import get_db
from models.domain import SocialAccount, User
from services.ml_engagement import engagement_predictor

router = APIRouter()
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _next_optimal(day_index: int, hour: int) -> str:
    now = datetime.utcnow()
    days_ahead = (day_index - now.weekday()) % 7
    candidate = now + timedelta(days=days_ahead)
    candidate = candidate.replace(hour=hour, minute=0, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=7)
    return candidate.isoformat()


@router.post("/predict")
async def predict_timing(
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Predict best posting windows from the engagement model."""
    platform = payload.get("platform", "instagram")
    content_type = payload.get("content_type", "image")
    n_slots = int(payload.get("n_slots", 5))
    account_id = payload.get("account_id")

    followers = 10000
    historical_avg_er = 0.03
    if account_id:
        result = await db.execute(
            select(SocialAccount).where(
                SocialAccount.id == uuid.UUID(str(account_id)),
                SocialAccount.user_id == current_user.id,
            )
        )
        account = result.scalar_one_or_none()
        if account:
            followers = account.followers_count or followers
            historical_avg_er = (account.metadata_ or {}).get("avg_er", 0.03)

    weekly_heatmap = [
        [
            round(
                engagement_predictor.predict(
                    platform=platform,
                    content_type=content_type,
                    hour=hour,
                    day_of_week=day,
                    followers=followers,
                    historical_avg_er=historical_avg_er,
                ).predicted_engagement_rate * 100,
                2,
            )
            for hour in range(24)
        ]
        for day in range(7)
    ]

    ranked = []
    for day in range(7):
        for hour in range(24):
            ranked.append({
                "day_of_week": day,
                "day_name": DAY_NAMES[day],
                "hour": hour,
                "predicted_engagement_score": weekly_heatmap[day][hour],
                "label": f"{DAY_NAMES[day]} {hour:02d}:00",
            })
    ranked.sort(key=lambda item: item["predicted_engagement_score"], reverse=True)
    best = ranked[0]

    return {
        "platform": platform,
        "content_type": content_type,
        "account_id": account_id or "",
        "top_slots": ranked[:max(1, n_slots)],
        "weekly_heatmap": weekly_heatmap,
        "next_optimal": _next_optimal(best["day_of_week"], best["hour"]),
        "ramadan_adjusted": False,
    }
