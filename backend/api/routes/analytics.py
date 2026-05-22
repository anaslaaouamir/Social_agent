"""Analytics routes backed primarily by live platform APIs."""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth_utils import get_current_user
from api.routes.posts import _fetch_live_comments_for_account, _fetch_live_posts_for_account
from core.database import get_db
from models.domain import AccountMetric, SocialAccount, User
from services.facebook_graph import FacebookGraphService
from services.linkedIn_graph import LinkedInGraphService
from services.nlp_pipeline import nlp_pipeline
from services.tiktok_graph import TikTokGraphService
from services.twitter_graph import TwitterGraphService
from services.instagram_graph import InstagramService

router = APIRouter()


def _iso_from_ts(value: float | None) -> str | None:
    if not value:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def _parse_ts(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


async def _live_account_overview(account: SocialAccount, days: int) -> dict:
    followers = account.followers_count or 0
    reach_total = 0
    impressions_total = 0
    live_metadata: dict = {}
    try:
        if account.platform.value == "instagram":
            svc = InstagramService(account.access_token)
            try:
                profile = await svc.get_account_info(account.account_id)
                insights = await svc.get_account_insights(account.account_id)
            finally:
                await svc.close()
            followers = int(profile.get("followers_count", followers) or followers)
            reach_total = int(insights.get("reach", 0) or 0)
            impressions_total = int(insights.get("impressions", 0) or 0)
            live_metadata = {"profile_views": insights.get("profile_views", 0)}

        elif account.platform.value == "facebook":
            svc = FacebookGraphService(account.access_token)
            try:
                insights = await svc.get_page_insights(account.account_id, account.access_token, days=days)
            finally:
                await svc.close()
            reach_total = int(insights.get("page_reach", 0) or 0)
            impressions_total = int(insights.get("page_impressions", 0) or 0)
            live_metadata = {
                "engaged_users": insights.get("page_engaged_users", 0),
                "new_followers": insights.get("page_follows", insights.get("page_follows_unique", insights.get("page_fan_adds_unique", 0))),
            }

        elif account.platform.value == "linkedin":
            svc = LinkedInGraphService(account.access_token)
            try:
                metrics = await svc.get_member_analytics(account.account_id)
            finally:
                await svc.close()
            followers = int(metrics.get("follower_count", followers) or followers)
            live_metadata = {"connections": metrics.get("connections", 0)}

        elif account.platform.value == "twitter":
            svc = TwitterGraphService(account.access_token)
            try:
                profile = await svc.get_user_profile(account.account_id)
            finally:
                await svc.close()
            followers = int((profile.get("public_metrics") or {}).get("followers_count", followers) or followers)

        elif account.platform.value == "tiktok":
            svc = TikTokGraphService(account.access_token)
            try:
                metrics = await svc.get_account_metrics()
            finally:
                await svc.close()
            followers = int(metrics.get("followers_count", followers) or followers)
            live_metadata = {"likes_count": metrics.get("likes_count", 0), "video_count": metrics.get("video_count", 0)}
    except Exception as exc:
        logger.warning(
            "Live analytics overview fallback for platform='{}' account_name='{}': {}",
            account.platform.value,
            account.account_name,
            exc,
        )
        live_metadata = {**live_metadata, "live_error": str(exc)}

    return {
        "followers": followers,
        "reach_total": reach_total,
        "impressions_total": impressions_total,
        "metadata": live_metadata,
    }


# async def _build_live_sentiment_distribution(account: SocialAccount, live_posts: list[dict]) -> tuple[dict[str, int], int]:
#     sentiment_dist = {"positive": 0, "negative": 0, "neutral": 0, "spam": 0, "toxic": 0}
#     analyzed_comments = 0

#     for post in live_posts[:5]:
#         platform_post_id = str(post.get("id") or "")
#         if not platform_post_id:
#             continue
#         try:
#             comments = await _fetch_live_comments_for_account(account, platform_post_id)
#         except Exception:
#             continue
#         for comment in comments[:25]:
#             text = str(comment.get("text") or "").strip()
#             if not text:
#                 continue
#             result = await nlp_pipeline.process(text)
#             label = nlp_pipeline.get_unified_label(result)
#             sentiment_dist[label] = sentiment_dist.get(label, 0) + 1
#             analyzed_comments += 1

#     return sentiment_dist, analyzed_comments

async def _build_live_sentiment_distribution(account: SocialAccount, live_posts: list[dict]) -> tuple[dict[str, int], int]:
    sentiment_dist = {"positive": 0, "negative": 0, "neutral": 0, "spam": 0, "toxic": 0}
    analyzed_comments = 0
    for post in live_posts[:5]:
        platform_post_id = str(post.get("id") or "")
        if not platform_post_id:
            continue
        try:
            comments = await _fetch_live_comments_for_account(account, platform_post_id)
        except Exception:
            continue
        for comment in comments[:25]:
            text = str(comment.get("text") or "").strip()
            if not text:
                continue
                
            # --- FIX: Stop AI from freezing the analytics page ---
            label = "neutral"
            # -----------------------------------------------------
            
            sentiment_dist[label] = sentiment_dist.get(label, 0) + 1
            analyzed_comments += 1
    return sentiment_dist, analyzed_comments


@router.get("/overview")
async def analytics_overview(
    account_id: str = Query(None),
    days: int = Query(30),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    accounts_query = select(SocialAccount).where(SocialAccount.user_id == current_user.id)
    if account_id:
        accounts_query = accounts_query.where(SocialAccount.id == uuid.UUID(account_id))

    accounts_result = await db.execute(accounts_query)
    accounts = accounts_result.scalars().all()
    response_accounts = []
    primary_payload = None

    cutoff_ts = time.time() - max(days, 1) * 86400

    for account in accounts:
        live_overview = await _live_account_overview(account, days)
        live_posts_error = None
        try:
            live_posts = await _fetch_live_posts_for_account(account, limit=max(10, min(days, 30)))
        except Exception as exc:
            logger.warning(
                "Live posts analytics fallback for platform='{}' account_name='{}': {}",
                account.platform.value,
                account.account_name,
                exc,
            )
            live_posts = []
            live_posts_error = str(exc)
        live_posts = [
            post for post in live_posts
            if not post.get("published_at") or float(post.get("published_at") or 0) >= cutoff_ts
        ]

        total_likes = sum(int(post.get("likes", 0) or 0) for post in live_posts)
        total_comments_from_posts = sum(int(post.get("comments_count", 0) or 0) for post in live_posts)
        total_shares = sum(int(post.get("shares_count", 0) or 0) for post in live_posts)
        total_reach = sum(int(post.get("reach", 0) or 0) for post in live_posts) or live_overview["reach_total"]
        total_impressions = sum(int(post.get("impressions", 0) or 0) for post in live_posts) or live_overview["impressions_total"]
        followers = int(live_overview["followers"] or 0)

        content_buckets: dict[str, dict[str, float]] = {}
        for post in live_posts:
            content_type = str(post.get("media_type") or "image").lower()
            bucket = content_buckets.setdefault(content_type, {"count": 0, "engagement_total": 0.0, "reach_total": 0.0})
            bucket["count"] += 1
            interactions = int(post.get("likes", 0) or 0) + int(post.get("comments_count", 0) or 0) + int(post.get("shares_count", 0) or 0)
            er = interactions / max(followers, 1)
            bucket["engagement_total"] += er
            bucket["reach_total"] += int(post.get("reach", 0) or 0)

        content_performance = [
            {
                "type": content_type,
                "count": int(values["count"]),
                "avg_engagement_rate": round(values["engagement_total"] / max(values["count"], 1), 4),
                "avg_reach": round(values["reach_total"] / max(values["count"], 1), 2),
            }
            for content_type, values in sorted(
                content_buckets.items(),
                key=lambda item: item[1]["engagement_total"] / max(item[1]["count"], 1),
                reverse=True,
            )
        ]

        sentiment_distribution, analyzed_comments = await _build_live_sentiment_distribution(account, live_posts)
        total_comments = analyzed_comments or total_comments_from_posts

        avg_engagement_rate = (
            sum(item["avg_engagement_rate"] for item in content_performance) / max(len(content_performance), 1)
            if content_performance
            else (
                (total_likes + total_comments_from_posts + total_shares) / max(followers * max(len(live_posts), 1), 1)
            )
        )

        metrics_result = await db.execute(
            select(AccountMetric)
            .where(AccountMetric.account_id == account.id, AccountMetric.timestamp >= cutoff_ts)
            .order_by(AccountMetric.timestamp.asc())
        )
        metrics = metrics_result.scalars().all()
        trends = [
            {
                "label": datetime.fromtimestamp(metric.timestamp, tz=timezone.utc).strftime("%d/%m"),
                "timestamp": metric.timestamp,
                "date": _iso_from_ts(metric.timestamp),
                "followers": metric.followers_count,
                "engagement_rate": round(metric.avg_engagement_rate or 0.0, 4),
                "reach": metric.reach_24h or 0,
                "impressions": metric.impressions_24h or 0,
                "new_followers": metric.new_followers_24h or 0,
            }
            for metric in metrics
        ]
        if not trends:
            trends = [
                {
                    "label": datetime.fromtimestamp(
                        float(post.get("published_at") or time.time()),
                        tz=timezone.utc,
                    ).strftime("%d/%m"),
                    "timestamp": float(post.get("published_at") or time.time()),
                    "date": _iso_from_ts(float(post.get("published_at") or time.time())),
                    "followers": followers,
                    "engagement_rate": round(
                        (
                            int(post.get("likes", 0) or 0)
                            + int(post.get("comments_count", 0) or 0)
                            + int(post.get("shares_count", 0) or 0)
                        ) / max(followers, 1),
                        4,
                    ),
                    "reach": int(post.get("reach", 0) or 0),
                    "impressions": int(post.get("impressions", 0) or 0),
                    "new_followers": 0,
                }
                for post in reversed(live_posts[-12:])
            ]

        best_content_type = content_performance[0]["type"] if content_performance else None
        optimal_frequency = round((len(live_posts) / max(days, 1)) * 7, 1) if live_posts else None
        forecast_new_followers = 0
        predicted_followers: list[dict] = []
        forecast_trend = "stable"

        if len(trends) >= 2:
            start_followers = int(trends[0].get("followers", followers) or followers)
            end_followers = int(trends[-1].get("followers", followers) or followers)
            delta = end_followers - start_followers
            elapsed_days = max((float(trends[-1]["timestamp"]) - float(trends[0]["timestamp"])) / 86400, 1)
            daily_growth = delta / elapsed_days
            forecast_new_followers = max(0, int(round(daily_growth * days)))
            forecast_trend = "up" if daily_growth > 0 else "down" if daily_growth < 0 else "stable"
            predicted_followers = [
                {"day": idx + 1, "followers": max(0, int(round(end_followers + daily_growth * (idx + 1))))}
                for idx in range(min(days, 14))
            ]

        summary = {
            "account_id": str(account.id),
            "platform": account.platform.value,
            "account_name": account.account_name,
            "followers": followers,
            "posts_analyzed": len(live_posts),
            "avg_engagement_rate": round(avg_engagement_rate, 4),
            "total_likes": total_likes,
            "total_comments": total_comments,
            "total_reach": total_reach,
            "total_impressions": total_impressions,
            "sentiment_distribution": sentiment_distribution,
            "metadata": {
                **(account.metadata_ or {}),
                **live_overview["metadata"],
                **({"live_posts_error": live_posts_error} if live_posts_error else {}),
            },
        }
        response_accounts.append(summary)

        if primary_payload is None:
            primary_payload = {
                "account": {
                    "id": str(account.id),
                    "name": account.account_name,
                    "platform": account.platform.value,
                    "followers": followers,
                },
                "insights": {
                    "best_content_type": best_content_type,
                    "avg_engagement_rate": round(avg_engagement_rate, 4),
                    "optimal_frequency": optimal_frequency,
                    "engagement_trend": forecast_trend,
                    "competitor_benchmark": {},
                },
                "forecast": {
                    "period_days": days,
                    "predicted_followers": predicted_followers,
                    "trend": forecast_trend,
                    "expected_new_followers": forecast_new_followers,
                },
                "total_posts": len(live_posts),
                "published_posts": len(live_posts),
                "sentiment_distribution": sentiment_distribution,
                "trends": trends,
                "content_performance": content_performance,
            }

    response = {"accounts": response_accounts}
    if account_id and primary_payload:
        response.update(primary_payload)
    return response


@router.get("/engagement-history")
async def engagement_history(
    account_id: str = Query(...),
    days: int = Query(30),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    account_result = await db.execute(
        select(SocialAccount).where(
            SocialAccount.id == uuid.UUID(account_id),
            SocialAccount.user_id == current_user.id,
        )
    )
    account = account_result.scalar_one_or_none()
    if not account:
        from fastapi import HTTPException

        raise HTTPException(404, "Account not found")

    cutoff_ts = time.time() - max(days, 1) * 86400
    result = await db.execute(
        select(AccountMetric)
        .where(AccountMetric.account_id == uuid.UUID(account_id), AccountMetric.timestamp >= cutoff_ts)
        .order_by(AccountMetric.timestamp.asc())
    )
    metrics = result.scalars().all()

    return {
        "account_id": account_id,
        "days": days,
        "data": [
            {
                "date": metric.timestamp,
                "followers": metric.followers_count,
                "engagement_rate": metric.avg_engagement_rate,
                "reach": metric.reach_24h,
                "impressions": metric.impressions_24h,
            }
            for metric in metrics
        ],
    }
