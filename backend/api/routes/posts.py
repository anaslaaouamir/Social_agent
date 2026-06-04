"""Posts router: create, read, update, delete, schedule, AI-generate."""
from __future__ import annotations
import base64
import binascii
import hashlib
import hmac
import re
import time
import uuid
from typing import Optional
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from pydantic import BaseModel
from core.config import get_settings
from core.database import get_db
from models.domain import AlertSeverity, User, Post, PostStatus, ContentType, SocialAccount, Platform
from api.auth_utils import get_current_user
from services.facebook_graph import FacebookGraphService
from services.instagram_graph import InstagramService
from services.linkedIn_graph import LinkedInGraphService
from services.ml_engagement import engagement_predictor
from services.nlp_pipeline import nlp_pipeline
from services.social_activity_store import (
    ensure_activity_alert,
    ensure_negative_comment_alert,
    persist_live_comment,
    persist_live_post,
)
from services.tiktok_graph import TikTokGraphService
from services.threads_graph import ThreadsGraphService
from services.twitter_graph import TwitterGraphService
from services.youtube_graph import YouTubeGraphService

import os
import uuid
import shutil
from fastapi import UploadFile, File

router = APIRouter()
settings = get_settings()


def _is_public_http_url(value: str) -> bool:

    if value.startswith("/media/"):
        return True
    
    try:
        parsed = urlparse(value)
    except Exception:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _is_data_image_url(value: str) -> bool:
    return value.startswith("data:image/") and ";base64," in value


def _is_data_media_url(value: str) -> bool:
    return value.startswith("data:") and ";base64," in value


def _validate_media_urls_for_platform(platform: str, media_urls: list[str]) -> None:
    if not media_urls:
        return

    # if platform == "facebook":
    #     invalid = [url for url in media_urls if not (_is_public_http_url(url) or _is_data_image_url(url))]
    #     if not invalid:
    #         return
    #     raise HTTPException(
    #         400,
    #         "Facebook media posts require either a public http(s) URL or a base64 data:image URL from the media library. Blob URLs and local file paths are not supported.",
    #     )
    #     return

    invalid = [url for url in media_urls if not (_is_public_http_url(url) or _is_data_media_url(url))]
    if invalid:
        raise HTTPException(
            400,
            f"{platform.title()} media posts require either a public http(s) URL or a base64 data: URL from the media library. Blob URLs and local file paths are not supported.",
        )


def _parse_data_url(value: str) -> tuple[str, bytes] | None:
    if not value.startswith("data:") or ";base64," not in value:
        return None
    header, raw = value.split(",", 1)
    mime_type = header[5:].split(";", 1)[0]
    try:
        return mime_type, base64.b64decode(raw)
    except (binascii.Error, ValueError):
        return None


def _build_media_token(post_id: str, media_index: int, expires: int, media_url: str) -> str:
    payload = f"{post_id}:{media_index}:{expires}:{hashlib.sha256(media_url.encode('utf-8')).hexdigest()}"
    return hmac.new(
        settings.secret_key.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


class PostCreate(BaseModel):
    account_id: str
    content_type: str = "image"
    caption: Optional[str] = None
    hashtags: list[str] = []
    media_urls: list[str] = []
    scheduled_at: Optional[float] = None


class PostUpdate(BaseModel):
    content_type: Optional[str] = None
    caption: Optional[str] = None
    hashtags: Optional[list[str]] = None
    media_urls: Optional[list[str]] = None
    scheduled_at: Optional[float] = None
    status: Optional[str] = None


class PostOut(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    content_type: str
    status: str
    caption: Optional[str]
    hashtags: list
    media_urls: list
    scheduled_at: Optional[float]
    published_at: Optional[float]
    platform_post_id: Optional[str]
    ai_quality_score: Optional[float]
    ai_predicted_engagement: Optional[float]
    likes_count: int
    comments_count: int
    shares_count: int
    reach: int
    engagement_rate: float
    visual_analysis: dict
    ai_caption_variants: list

    model_config = {"from_attributes": True}


def _parse_datetime_to_ts(value: str | None) -> float | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        normalized = raw.replace("Z", "+00:00")
        return __import__("datetime").datetime.fromisoformat(normalized).timestamp()
    except ValueError:
        return None


def _infer_content_type(media_type: str | None) -> str:
    value = str(media_type or "").lower()
    if value in {"video", "reel", "reels"}:
        return "reel" if value in {"reel", "reels"} else "video"
    if value == "carousel_album":
        return "carousel"
    if value == "story":
        return "story"
    return "image"


def _text_feature_flags(text: str) -> dict[str, int | bool]:
    content = text or ""
    return {
        "caption_length": len(content),
        "hashtag_count": len(re.findall(r"#\w+", content)),
        "has_emoji": bool(re.search(r"[\U0001F300-\U0001FAFF]", content)),
        "has_mention": bool(re.search(r"@\w+", content)),
        "has_question": "?" in content,
    }


def _label_color(label: str) -> str:
    return {
        "spam": "gray",
        "toxic": "red",
        "positive": "green",
        "negative": "orange",
        "neutral": "blue",
    }.get(label, "blue")


# async def _enrich_live_comment(comment: dict) -> dict:
#     text = str(comment.get("text") or "").strip()
#     if not text:
#         comment["label"] = "neutral"
#         comment["label_color"] = _label_color("neutral")
#         comment["sentiment_score"] = 0.0
#         comment["is_spam"] = False
#         comment["is_toxic"] = False
#         return comment

#     result = await nlp_pipeline.process(text)
#     label = nlp_pipeline.get_unified_label(result)
#     priority = round(
#         max(result.spam_score, result.toxic_score, abs(result.sentiment_score)),
#         4,
#     )
#     comment.update(
#         {
#             "label": label,
#             "label_color": _label_color(label),
#             "sentiment_score": result.sentiment_score,
#             "spam_score": result.spam_score,
#             "toxic_score": result.toxic_score,
#             "is_spam": result.is_spam,
#             "is_toxic": result.is_toxic,
#             "reply_priority": priority,
#             "language": result.language,
#         }
#     )
#     return comment

async def _enrich_live_comment(comment: dict) -> dict:
    text = str(comment.get("text") or "").strip()
    
    # We assign default neutral values immediately instead of waiting for the AI models.
    # This prevents the API from freezing while trying to analyze dozens of comments.
    comment.update({
        "label": "neutral",
        "label_color": _label_color("neutral"),
        "sentiment_score": 0.0,
        "spam_score": 0.0,
        "toxic_score": 0.0,
        "is_spam": False,
        "is_toxic": False,
        "reply_priority": 0.0,
        "language": "unknown",
    })
    return comment


def _enrich_live_post(account: SocialAccount, post: dict) -> dict:
    published_at = post.get("published_at")
    dt = __import__("datetime").datetime.fromtimestamp(published_at) if published_at else __import__("datetime").datetime.utcnow()
    features = _text_feature_flags(str(post.get("text") or ""))
    try:
        prediction = engagement_predictor.predict(
            platform=account.platform.value,
            content_type=_infer_content_type(post.get("media_type")),
            hour=dt.hour,
            day_of_week=dt.weekday(),
            caption_length=int(features["caption_length"]),
            hashtag_count=int(features["hashtag_count"]),
            has_emoji=bool(features["has_emoji"]),
            has_mention=bool(features["has_mention"]),
            has_question=bool(features["has_question"]),
            followers=account.followers_count or 10000,
            historical_avg_er=float((account.metadata_ or {}).get("avg_er", 0.03)),
        )
        post.update(
            {
                "predicted_engagement_rate": prediction.predicted_engagement_rate,
                "predicted_engagement_percent": round(prediction.predicted_engagement_rate * 100, 2),
            }
        )
    except Exception as exc:
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "Engagement prediction failed for post %s on %s: %s",
            post.get("id"), account.platform.value, exc,
        )
        post.update({
            "predicted_engagement_rate": 0.03,
            "predicted_engagement_percent": 3.0,
        })
    return post


async def _persist_live_post_dict(db: AsyncSession, account: SocialAccount, post: dict) -> Post:
    return await persist_live_post(
        db,
        account_id=account.id,
        platform_post_id=str(post.get("id") or ""),
        content_type=_infer_content_type(post.get("media_type")),
        text=str(post.get("text") or ""),
        media_url=post.get("media_url"),
        published_at=post.get("published_at"),
        likes=int(post.get("likes") or 0),
        comments_count=int(post.get("comments_count") or 0),
        shares_count=int(post.get("shares_count") or 0),
        reach=int(post.get("reach") or 0),
        impressions=int(post.get("impressions") or 0),
    )


async def _fetch_live_posts_for_account(account: SocialAccount, limit: int = 20) -> list[dict]:
    if account.platform == Platform.INSTAGRAM:
        svc = InstagramService(account.access_token)
        try:
            media = await svc.get_media(account.account_id, limit=limit)
        finally:
            await svc.close()
        return [
            {
                "id": item.get("id"),
                "account_id": str(account.id),
                "platform": account.platform.value,
                "account_name": account.account_name,
                "text": item.get("caption", ""),
                "timestamp": item.get("timestamp"),
                "published_at": _parse_datetime_to_ts(item.get("timestamp")),
                "likes": item.get("like_count", 0),
                "comments_count": item.get("comments_count", 0),
                "shares_count": 0,
                "media_url": item.get("media_url") or item.get("thumbnail_url"),
                "media_type": str(item.get("media_type", "IMAGE")).lower(),
                "permalink": item.get("permalink"),
            }
            for item in media
        ]

    if account.platform == Platform.FACEBOOK:
        svc = FacebookGraphService(account.access_token)
        try:
            posts = await svc.get_page_posts(account.account_id, account.access_token, limit=limit)
        finally:
            await svc.close()
        return [
            {
                "id": item.get("id"),
                "account_id": str(account.id),
                "platform": account.platform.value,
                "account_name": account.account_name,
                "text": item.get("message", ""),
                "timestamp": item.get("created_time"),
                "published_at": _parse_datetime_to_ts(item.get("created_time")),
                "likes": item.get("likes", 0),
                "comments_count": item.get("comments", 0),
                "shares_count": item.get("shares", 0),
                "media_url": item.get("picture"),
                "media_type": "image" if item.get("picture") else None,
                "permalink": item.get("url"),
            }
            for item in posts
        ]

    if account.platform == Platform.LINKEDIN:
        svc = LinkedInGraphService(account.access_token)
        try:
            posts = await svc.get_member_posts(account.account_id, count=limit)
        finally:
            await svc.close()
        return [
            {
                "id": item.get("id"),
                "account_id": str(account.id),
                "platform": account.platform.value,
                "account_name": account.account_name,
                "text": item.get("text", ""),
                "timestamp": item.get("created_at"),
                "published_at": _parse_datetime_to_ts(item.get("created_at")),
                "likes": item.get("likes", 0),
                "comments_count": item.get("comments", 0),
                "shares_count": item.get("reposts", 0),
                "media_url": None,
                "media_type": None,
                "permalink": None,
            }
            for item in posts
        ]

    if account.platform == Platform.TWITTER:
        svc = TwitterGraphService(account.access_token)
        try:
            tweets = await svc.get_user_tweets(account.account_id, max_results=limit)
        finally:
            await svc.close()
        return [
            {
                "id": item.get("id"),
                "account_id": str(account.id),
                "platform": account.platform.value,
                "account_name": account.account_name,
                "text": item.get("text", ""),
                "timestamp": item.get("created_at"),
                "published_at": _parse_datetime_to_ts(item.get("created_at")),
                "likes": (item.get("public_metrics") or {}).get("like_count", 0),
                "comments_count": (item.get("public_metrics") or {}).get("reply_count", 0),
                "shares_count": (item.get("public_metrics") or {}).get("retweet_count", 0),
                "media_url": None,
                "media_type": None,
                "permalink": None,
            }
            for item in tweets
        ]

    if account.platform == Platform.TIKTOK:
        svc = TikTokGraphService(account.access_token)
        try:
            videos = await svc.get_user_videos(max_count=limit)
        finally:
            await svc.close()
        return [
            {
                "id": item.get("id"),
                "account_id": str(account.id),
                "platform": account.platform.value,
                "account_name": account.account_name,
                "text": item.get("video_description") or item.get("title", ""),
                "timestamp": item.get("create_time"),
                "published_at": _parse_datetime_to_ts(item.get("create_time")),
                "likes": item.get("like_count", 0),
                "comments_count": item.get("comment_count", 0),
                "shares_count": item.get("share_count", 0),
                "media_url": item.get("cover_image_url"),
                "media_type": "video",
                "permalink": item.get("share_url"),
            }
            for item in videos
        ]

    if account.platform == Platform.THREADS:
        svc = ThreadsGraphService(account.access_token)
        try:
            threads = await svc.get_threads(account.account_id, limit=limit)
            
            results = []
            for item in threads:
                media_id = item.get("id")
                try:
                    insights = await svc.get_media_insights(media_id)
                except Exception:
                    insights = {}
                    
                results.append({
                    "id": media_id,
                    "account_id": str(account.id),
                    "platform": account.platform.value,
                    "account_name": account.account_name,
                    "text": item.get("text", ""),
                    "timestamp": item.get("timestamp"),
                    "published_at": _parse_datetime_to_ts(item.get("timestamp")),
                    "likes": insights.get("likes", 0),
                    "comments_count": insights.get("replies", 0),
                    "shares_count": insights.get("reposts", 0) + insights.get("quotes", 0),
                    "media_url": item.get("media_url"),
                    "media_type": str(item.get("media_type") or "").lower() or None,
                    "permalink": item.get("permalink"),
                })
            return results
        finally:
            await svc.close()

    if account.platform == Platform.YOUTUBE:
        svc = YouTubeGraphService(account.access_token)
        try:
            videos = await svc.get_channel_videos(account.account_id, max_results=limit)
        finally:
            await svc.close()
        return [
            {
                "id": item.get("id"),
                "account_id": str(account.id),
                "platform": account.platform.value,
                "account_name": account.account_name,
                "text": (item.get("snippet") or {}).get("title", ""),
                "timestamp": (item.get("snippet") or {}).get("publishedAt"),
                "published_at": _parse_datetime_to_ts((item.get("snippet") or {}).get("publishedAt")),
                "likes": int((item.get("statistics") or {}).get("likeCount", 0) or 0),
                "comments_count": int((item.get("statistics") or {}).get("commentCount", 0) or 0),
                "shares_count": 0,
                "reach": int((item.get("statistics") or {}).get("viewCount", 0) or 0),
                "impressions": int((item.get("statistics") or {}).get("viewCount", 0) or 0),
                "media_url": (((item.get("snippet") or {}).get("thumbnails") or {}).get("high") or {}).get("url"),
                "media_type": "video",
                "permalink": f"https://www.youtube.com/watch?v={item.get('id')}",
            }
            for item in videos
        ]

    return []


async def _fetch_live_comments_for_account(account: SocialAccount, platform_post_id: str) -> list[dict]:
    if account.platform == Platform.INSTAGRAM:
        svc = InstagramService(account.access_token)
        try:
            comments = await svc.get_comments(platform_post_id)
        finally:
            await svc.close()
        return [
            {
                "id": item.get("id"),
                "author": item.get("username", "Instagram user"),
                "text": item.get("text", ""),
                "timestamp": item.get("timestamp"),
                "likes": item.get("like_count", 0),
                "platform": account.platform.value,
                "can_reply": True,
                "reply_mode": "comment",
                "reply_target_id": item.get("id"),
                "reply_parent_id": platform_post_id,
                "reply_action_label": "Repondre au commentaire",
            }
            for item in comments
        ]

    if account.platform == Platform.FACEBOOK:
        import httpx
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"https://graph.facebook.com/v20.0/{platform_post_id}/comments",
                params={
                    "access_token": account.access_token,
                    "fields": "id,message,from,created_time,like_count",
                    "summary": "true",
                },
            )
        data = resp.json()
        if "error" in data:
            raise HTTPException(400, f"Facebook API error: {data['error']['message']}")
        return [
            {
                "id": item.get("id"),
                "author": (item.get("from") or {}).get("name", "Facebook user"),
                "text": item.get("message", ""),
                "timestamp": item.get("created_time"),
                "likes": item.get("like_count", 0),
                "platform": account.platform.value,
                "can_reply": True,
                "reply_mode": "comment",
                "reply_target_id": item.get("id"),
                "reply_parent_id": platform_post_id,
                "reply_action_label": "Repondre au commentaire",
            }
            for item in data.get("data", [])
        ]

    if account.platform == Platform.LINKEDIN:
        svc = LinkedInGraphService(account.access_token)
        try:
            comments = await svc.get_post_comments(platform_post_id)
        finally:
            await svc.close()
        return [
            {
                "id": item.get("id"),
                "author": item.get("actor", "LinkedIn member"),
                "text": item.get("text", ""),
                "timestamp": item.get("created_at"),
                "likes": item.get("likes", 0),
                "platform": account.platform.value,
                "can_reply": True,
                "reply_mode": "comment",
                "reply_target_id": item.get("id"),
                "reply_parent_id": platform_post_id,
                "reply_action_label": "Commenter sur le post",
            }
            for item in comments
        ]

    if account.platform == Platform.YOUTUBE:
        svc = YouTubeGraphService(account.access_token)
        try:
            comments = await svc.get_video_comments(platform_post_id)
        finally:
            await svc.close()
        return [
            {
                "id": item.get("id"),
                "author": (
                    (item.get("snippet") or {})
                    .get("topLevelComment", {})
                    .get("snippet", {})
                    .get("authorDisplayName", "YouTube user")
                ),
                "text": (
                    (item.get("snippet") or {})
                    .get("topLevelComment", {})
                    .get("snippet", {})
                    .get("textDisplay", "")
                ),
                "timestamp": (
                    (item.get("snippet") or {})
                    .get("topLevelComment", {})
                    .get("snippet", {})
                    .get("publishedAt")
                ),
                "likes": int(
                    (item.get("snippet") or {})
                    .get("topLevelComment", {})
                    .get("snippet", {})
                    .get("likeCount", 0)
                    or 0
                ),
                "platform": account.platform.value,
                "can_reply": True,
                "reply_mode": "comment",
                "reply_target_id": item.get("id"),
                "reply_parent_id": platform_post_id,
                "reply_action_label": "Repondre au commentaire",
            }
            for item in comments
        ]

    return []


async def _enrich_and_store_live_comment(
    db: AsyncSession,
    account: SocialAccount,
    post: Post,
    comment: dict,
) -> dict:
    enriched = await _enrich_live_comment(comment)
    label = None
    is_question = "?" in str(enriched.get("text") or "")
    is_lead = any(
        token in str(enriched.get("text") or "").lower()
        for token in ("prix", "price", "tarif", "commande", "devis", "buy", "acheter")
    )
    stored = await persist_live_comment(
        db,
        post=post,
        comment=enriched,
        label=label,
        sentiment_score=float(enriched.get("sentiment_score") or 0.0),
        is_spam=bool(enriched.get("is_spam")),
        is_toxic=bool(enriched.get("is_toxic")),
        is_question=is_question,
        is_lead=is_lead,
        reply_priority=int(enriched.get("reply_priority") or 0),
    )
    enriched["stored_comment_id"] = str(stored.id)
    
    # --- ADD THIS TO SYNC WITH DATABASE ---
    if stored.sentiment:
        enriched["label"] = stored.sentiment.value
        enriched["is_toxic"] = stored.sentiment.value == "toxic"
        enriched["is_spam"] = stored.sentiment.value == "spam"
        enriched["sentiment_score"] = stored.sentiment_score
        
    if label in {"negative", "toxic"} or enriched.get("is_toxic"):
        await ensure_negative_comment_alert(db, account_id=account.id, post=post, comment=stored, platform=account.platform)
    return enriched


@router.get("/", response_model=list[PostOut])
async def list_posts(
    account_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(Post).join(SocialAccount).where(SocialAccount.user_id == current_user.id)
    if account_id:
        q = q.where(Post.account_id == uuid.UUID(account_id))
    if status:
        q = q.where(Post.status == PostStatus(status))
    q = q.order_by(Post.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/", response_model=PostOut, status_code=201)
async def create_post(
    data: PostCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify account ownership
    acc = await db.execute(
        select(SocialAccount).where(
            and_(SocialAccount.id == uuid.UUID(data.account_id),
                 SocialAccount.user_id == current_user.id)
        )
    )
    account = acc.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "Account not found")
    _validate_media_urls_for_platform(account.platform.value, data.media_urls)

    post = Post(
        id=uuid.uuid4(),
        account_id=uuid.UUID(data.account_id),
        content_type=ContentType(data.content_type),
        caption=data.caption,
        hashtags=data.hashtags,
        media_urls=data.media_urls,
        scheduled_at=data.scheduled_at,
        status=PostStatus.SCHEDULED if data.scheduled_at else PostStatus.DRAFT,
    )
    db.add(post)
    await db.flush()
    return post


@router.get("/live/feed")
async def list_live_posts(
    account_id: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(SocialAccount).where(SocialAccount.user_id == current_user.id)
    if account_id:
        query = query.where(SocialAccount.id == uuid.UUID(account_id))
    result = await db.execute(query)
    accounts = result.scalars().all()

    items: list[dict] = []
    errors: list[dict] = []
    for account in accounts:
        try:
            live_posts = await _fetch_live_posts_for_account(account, limit=limit)
            for post in live_posts:
                await _persist_live_post_dict(db, account, post)
                items.append(_enrich_live_post(account, post))
        except Exception as exc:
            errors.append(
                {
                    "account_id": str(account.id),
                    "platform": account.platform.value,
                    "account_name": account.account_name,
                    "error": str(exc),
                }
            )

    items.sort(key=lambda item: item.get("published_at") or 0, reverse=True)
    return {"items": items[: limit * max(len(accounts), 1)], "errors": errors}


@router.get("/live/comments")
async def list_live_comments(
    account_id: str = Query(...),
    platform_post_id: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SocialAccount).where(
            SocialAccount.id == uuid.UUID(account_id),
            SocialAccount.user_id == current_user.id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "Account not found")

    post_result = await db.execute(
        select(Post).where(Post.account_id == account.id, Post.platform_post_id == platform_post_id)
    )
    post = post_result.scalar_one_or_none()
    if post is None:
        post = await persist_live_post(
            db,
            account_id=account.id,
            platform_post_id=platform_post_id,
            content_type="image",
            text="",
        )

    comments = await _fetch_live_comments_for_account(account, platform_post_id)
    enriched_comments: list[dict] = []
    for comment in comments:
        try:
            enriched_comments.append(await _enrich_and_store_live_comment(db, account, post, comment))
        except Exception:
            comment["label"] = "neutral"
            comment["label_color"] = _label_color("neutral")
            comment["sentiment_score"] = 0.0
            comment["is_spam"] = False
            comment["is_toxic"] = False
            enriched_comments.append(comment)
    negative_count = sum(
        1 for comment in enriched_comments
        if comment.get("label") in {"negative", "toxic"} or comment.get("is_toxic")
    )
    total = len(enriched_comments)
    if total >= 5 and negative_count / max(total, 1) >= 0.5:
        await ensure_activity_alert(
            db,
            account_id=account.id,
            severity=AlertSeverity.CRITICAL if negative_count / total >= 0.75 else AlertSeverity.HIGH,
            alert_type="crisis_detected",
            title="Risque de crise commentaires",
            description=f"{negative_count}/{total} commentaires negatifs ou toxiques sur ce post.",
            metadata={
                "target_kind": "post",
                "target_key": f"crisis:{platform_post_id}",
                "account_id": str(account.id),
                "post_id": str(post.id),
                "platform_post_id": platform_post_id,
                "platform": account.platform.value,
                "negative_count": negative_count,
                "total": total,
                "negative_ratio": round(negative_count / total, 4),
                "action_url": f"/inbox?tab=posts&post={platform_post_id}&filter=negative",
            },
        )
    return {"items": enriched_comments}




@router.get("/{post_id}", response_model=PostOut)
async def get_post(
    post_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Post).join(SocialAccount)
        .where(Post.id == uuid.UUID(post_id), SocialAccount.user_id == current_user.id)
    )
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(404, "Post not found")
    return post


@router.get("/{post_id}/media/{media_index}")
async def serve_post_media(
    post_id: str,
    media_index: int,
    expires: int,
    token: str,
    db: AsyncSession = Depends(get_db),
):
    if expires < int(time.time()):
        raise HTTPException(410, "Media URL expired")

    result = await db.execute(select(Post).where(Post.id == uuid.UUID(post_id)))
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(404, "Post not found")

    if media_index < 0 or media_index >= len(post.media_urls):
        raise HTTPException(404, "Media not found")

    media_url = post.media_urls[media_index]
    expected_token = _build_media_token(post_id, media_index, expires, media_url)
    if not hmac.compare_digest(token, expected_token):
        raise HTTPException(403, "Invalid media token")

    parsed = _parse_data_url(media_url)
    if parsed is None:
        raise HTTPException(400, "Only media-library data URLs can be served from this endpoint")

    mime_type, raw_bytes = parsed
    return Response(content=raw_bytes, media_type=mime_type)


@router.patch("/{post_id}", response_model=PostOut)
async def update_post(
    post_id: str,
    data: PostUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Post, SocialAccount).join(SocialAccount)
        .where(Post.id == uuid.UUID(post_id), SocialAccount.user_id == current_user.id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(404, "Post not found")
    post, account = row
    if post.status == PostStatus.PUBLISHED:
        raise HTTPException(400, "Cannot edit a published post")

    provided_fields = getattr(data, "model_fields_set", set())

    if data.content_type is not None:
        post.content_type = ContentType(data.content_type)
    if data.caption is not None:
        post.caption = data.caption
    if data.hashtags is not None:
        post.hashtags = data.hashtags
    if data.media_urls is not None:
        post.media_urls = data.media_urls
    if "scheduled_at" in provided_fields:
        post.scheduled_at = data.scheduled_at
        post.status = PostStatus.SCHEDULED if data.scheduled_at else PostStatus.DRAFT
    if data.status:
        post.status = PostStatus(data.status)
    _validate_media_urls_for_platform(account.platform.value, post.media_urls)

    await db.flush()
    return post


@router.delete("/{post_id}", status_code=204)
async def delete_post(
    post_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Post).join(SocialAccount)
        .where(Post.id == uuid.UUID(post_id), SocialAccount.user_id == current_user.id)
    )
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(404, "Post not found")
    if post.status == PostStatus.PUBLISHED:
        raise HTTPException(400, "Cannot delete a published post")
    await db.delete(post)


@router.post("/{post_id}/publish", response_model=dict)
async def publish_now(
    post_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger immediate publish via Celery task."""
    result = await db.execute(
        select(Post).join(SocialAccount)
        .where(Post.id == uuid.UUID(post_id), SocialAccount.user_id == current_user.id)
    )
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(404, "Post not found")
    if post.status == PostStatus.PUBLISHED:
        raise HTTPException(400, "Already published")

    post.status = PostStatus.PUBLISHING
    await db.flush()

    # Enqueue Celery task
    try:
        from services.scheduler import publish_post_task
        publish_post_task.delay(str(post.id))
    except Exception as e:
        post.status = PostStatus.DRAFT
        raise HTTPException(500, f"Failed to enqueue: {e}")

    return {"status": "publishing", "post_id": post_id}


@router.post("/upload-video")
async def upload_video(file: UploadFile = File(...)):
    """Upload a video directly to the media folder."""
    os.makedirs("media", exist_ok=True)
    ext = file.filename.split('.')[-1] if '.' in file.filename else 'mp4'
    filename = f"{uuid.uuid4()}.{ext}"
    filepath = os.path.join("media", filename)
    
    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    return {"url": f"/media/{filename}"}