"""Real-time monitoring, pipeline status, and KPI aggregation."""
from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth_utils import get_current_user
from core.database import get_db
from core.runtime_state import runtime_state
from models.domain import (
    AccountMetric,
    Alert,
    AlertSeverity,
    Comment,
    Post,
    PostStatus,
    SentimentLabel,
    SocialAccount,
    User,
)

router = APIRouter()


def _dt_to_ts(value: datetime | None) -> float | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()


async def _pipeline_status(db: AsyncSession, account_ids: list) -> dict:
    now = time.time()

    latest_post_result = await db.execute(select(func.max(Post.updated_at)))
    latest_post_activity = _dt_to_ts(latest_post_result.scalar())

    latest_comment_result = await db.execute(select(func.max(Comment.created_at)))
    latest_comment_activity = _dt_to_ts(latest_comment_result.scalar())

    latest_metric_result = await db.execute(select(func.max(AccountMetric.timestamp)))
    latest_metric_ts = latest_metric_result.scalar()

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    processed_today_result = await db.execute(
        select(func.count(Comment.id)).where(
            Comment.sentiment.is_not(None),
            Comment.created_at >= today_start,
        )
    )
    processed_today = int(processed_today_result.scalar() or 0)

    scheduled_result = await db.execute(
        select(func.count(Post.id)).where(Post.status == PostStatus.SCHEDULED)
    )
    scheduled_posts = int(scheduled_result.scalar() or 0)

    app_started_at = runtime_state.get("app", {}).get("started_at")
    alert_started_at = runtime_state.get("alert_consumer", {}).get("started_at")

    return {
        "scheduler": {
            "status": "running" if runtime_state.get("app", {}).get("status") == "running" else "stopped",
            "last_run": latest_post_activity or app_started_at,
        },
        "publisher": {
            "status": "running" if runtime_state.get("app", {}).get("status") == "running" else "stopped",
            "queue_size": scheduled_posts,
        },
        "comment_monitor": {
            "status": "running" if runtime_state.get("app", {}).get("status") == "running" else "stopped",
            "last_scan": latest_comment_activity or app_started_at,
        },
        "sentiment_worker": {
            "status": "running" if runtime_state.get("app", {}).get("status") == "running" else "stopped",
            "processed_today": processed_today,
        },
        "analytics_worker": {
            "status": "running" if runtime_state.get("app", {}).get("status") == "running" else "stopped",
            "last_update": latest_metric_ts or app_started_at,
        },
        "alert_consumer": {
            "status": str(runtime_state.get("alert_consumer", {}).get("status", "unknown")),
            "last_run": alert_started_at or now,
        },
        "elasticsearch": {"status": str(runtime_state.get("elasticsearch", {}).get("status", "unknown"))},
        "redis": {"status": "healthy"},
        "kafka": {"status": str(runtime_state.get("kafka", {}).get("status", "unknown"))},
        "database": {"status": str(runtime_state.get("database", {}).get("status", "unknown"))},
    }


@router.get("/overview")
async def monitoring_overview(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    accounts_result = await db.execute(
        select(SocialAccount).where(SocialAccount.user_id == current_user.id)
    )
    accounts = accounts_result.scalars().all()
    account_ids = [account.id for account in accounts]

    pipeline = await _pipeline_status(db, account_ids)
    if not account_ids:
        return {
            "accounts": 0,
            "posts": {},
            "comments": {},
            "alerts": {},
            "pipeline": pipeline,
            "timestamp": time.time(),
        }

    posts_result = await db.execute(
        select(Post.status, func.count(Post.id))
        .where(Post.account_id.in_(account_ids))
        .group_by(Post.status)
    )
    posts_by_status = {row[0].value: row[1] for row in posts_result.all()}

    comments_result = await db.execute(
        select(Comment.sentiment, func.count(Comment.id))
        .join(Post, Comment.post_id == Post.id)
        .where(Post.account_id.in_(account_ids))
        .group_by(Comment.sentiment)
    )
    comments_by_sentiment = {
        (row[0].value if row[0] else "unanalyzed"): row[1]
        for row in comments_result.all()
    }

    alerts_result = await db.execute(
        select(Alert.severity, func.count(Alert.id))
        .where(
            Alert.account_id.in_(account_ids),
            Alert.is_acknowledged == False,  # noqa: E712
        )
        .group_by(Alert.severity)
    )
    alerts_by_severity = {row[0].value: row[1] for row in alerts_result.all()}

    return {
        "accounts": len(accounts),
        "total_followers": sum(account.followers_count for account in accounts),
        "platforms": [
            {
                "platform": account.platform.value,
                "account_name": account.account_name,
                "followers": account.followers_count,
            }
            for account in accounts
        ],
        "posts": posts_by_status,
        "comments": comments_by_sentiment,
        "alerts": alerts_by_severity,
        "pipeline": pipeline,
        "timestamp": time.time(),
    }


@router.get("/pipeline")
async def pipeline_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    accounts_result = await db.execute(
        select(SocialAccount.id).where(SocialAccount.user_id == current_user.id)
    )
    account_ids = list(accounts_result.scalars().all())
    return await _pipeline_status(db, account_ids)


@router.get("/kpis")
async def global_kpis(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    accounts_result = await db.execute(
        select(SocialAccount).where(SocialAccount.user_id == current_user.id)
    )
    accounts = accounts_result.scalars().all()
    account_ids = [account.id for account in accounts]

    if not account_ids:
        return {"error": "No accounts connected"}

    published_result = await db.execute(
        select(
            func.count(Post.id),
            func.avg(Post.engagement_rate),
            func.sum(Post.likes_count),
            func.sum(Post.comments_count),
            func.sum(Post.reach),
        )
        .where(
            Post.account_id.in_(account_ids),
            Post.status == PostStatus.PUBLISHED,
        )
    )
    total_posts, avg_er, total_likes, total_comments, total_reach = published_result.one()

    scheduled_result = await db.execute(
        select(func.count(Post.id)).where(
            Post.account_id.in_(account_ids),
            Post.status == PostStatus.SCHEDULED,
        )
    )
    scheduled = scheduled_result.scalar() or 0

    bad_comments_result = await db.execute(
        select(func.count(Comment.id))
        .join(Post, Comment.post_id == Post.id)
        .where(
            Post.account_id.in_(account_ids),
            Comment.sentiment.in_([SentimentLabel.TOXIC, SentimentLabel.NEGATIVE]),
        )
    )
    bad_comments = bad_comments_result.scalar() or 0

    critical_alerts_result = await db.execute(
        select(func.count(Alert.id)).where(
            Alert.account_id.in_(account_ids),
            Alert.severity == AlertSeverity.CRITICAL,
            Alert.is_acknowledged == False,  # noqa: E712
        )
    )
    critical_alerts = critical_alerts_result.scalar() or 0

    return {
        "total_accounts": len(accounts),
        "total_followers": sum(account.followers_count for account in accounts),
        "published_posts": int(total_posts or 0),
        "scheduled_posts": int(scheduled),
        "avg_engagement_rate": round(float(avg_er or 0) * 100, 2),
        "total_likes": int(total_likes or 0),
        "total_comments": int(total_comments or 0),
        "total_reach": int(total_reach or 0),
        "negative_comments": int(bad_comments),
        "critical_alerts": int(critical_alerts),
    }
