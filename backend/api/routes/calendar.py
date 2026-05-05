"""Content calendar router - scheduled posts by date range."""
from __future__ import annotations
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.database import get_db
from models.domain import User, Post, PostStatus, SocialAccount
from api.auth_utils import get_current_user

router = APIRouter()


@router.get("/")
async def get_calendar(
    start_ts: float = Query(..., description="Start timestamp (Unix)"),
    end_ts: float = Query(..., description="End timestamp (Unix)"),
    account_id: str = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all scheduled/published posts for a date range."""
    q = (
        select(Post, SocialAccount.platform, SocialAccount.account_name)
        .join(SocialAccount)
        .where(
            SocialAccount.user_id == current_user.id,
            Post.scheduled_at >= start_ts,
            Post.scheduled_at <= end_ts,
        )
    )
    if account_id:
        import uuid
        q = q.where(Post.account_id == uuid.UUID(account_id))
    q = q.order_by(Post.scheduled_at.asc())

    result = await db.execute(q)
    rows = result.all()

    return [
        {
            "id": str(post.id),
            "account_id": str(post.account_id),
            "platform": platform.value,
            "account_name": account_name,
            "content_type": post.content_type.value,
            "status": post.status.value,
            "caption_preview": (post.caption or "")[:100],
            "scheduled_at": post.scheduled_at,
            "published_at": post.published_at,
            "media_urls": post.media_urls[:1],  # first media only for preview
            "hashtags_count": len(post.hashtags),
            "predicted_engagement": post.ai_predicted_engagement,
        }
        for post, platform, account_name in rows
    ]


@router.get("/stats")
async def calendar_stats(
    start_ts: float = Query(...),
    end_ts: float = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Calendar period statistics."""
    q = (
        select(Post)
        .join(SocialAccount)
        .where(
            SocialAccount.user_id == current_user.id,
            Post.scheduled_at >= start_ts,
            Post.scheduled_at <= end_ts,
        )
    )
    result = await db.execute(q)
    posts = result.scalars().all()

    by_status = {}
    by_platform: dict[str, int] = {}
    for post in posts:
        s = post.status.value
        by_status[s] = by_status.get(s, 0) + 1

    return {
        "total": len(posts),
        "by_status": by_status,
        "period": {"start": start_ts, "end": end_ts},
    }
