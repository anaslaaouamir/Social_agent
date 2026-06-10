"""
Routes OAuth TikTok + synchronisation + publication.
Uses TikTok Login Kit (OAuth 2.0) with PKCE.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
import time
import uuid
from datetime import datetime
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth_utils import get_current_user
from core.config import get_settings
from core.database import get_db
from models.domain import AccountMetric, ContentType, Platform, Post, PostStatus, SocialAccount, User
from services.tiktok_graph import TikTokGraphService

router = APIRouter()
settings = get_settings()

TIKTOK_CLIENT_KEY    = settings.tiktok_client_key
TIKTOK_CLIENT_SECRET = settings.tiktok_client_secret
TIKTOK_REDIRECT_URI  = settings.tiktok_redirect_uri
FRONTEND_URL         = settings.frontend_url.rstrip("/")

TIKTOK_AUTH_URL  = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"

# Scopes needed: basic info + video list + publish
SCOPES = "user.info.basic,user.info.profile,user.info.stats,video.list,video.publish"

_oauth_state_store: dict[str, dict[str, str | float]] = {}


# ------------------------------------------------------------------ #
# Pydantic models                                                     #
# ------------------------------------------------------------------ #
class TikTokPublishIn(BaseModel):
    title: str
    video_url: str                          # public URL of the video to publish
    privacy_level: str = "PUBLIC_TO_EVERYONE"


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #
def _cleanup_state_store() -> None:
    now = time.time()
    expired = [k for k, v in _oauth_state_store.items() if float(v.get("expires_at", 0)) <= now]
    for k in expired:
        _oauth_state_store.pop(k, None)


def _build_code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def _parse_created_at(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _format_tiktok_account_name(profile: dict, fallback: str) -> str:
    raw_name = (
        profile.get("username")
        or profile.get("display_name")
        or profile.get("open_id")
        or fallback
    )
    raw_name = str(raw_name).strip()
    if not raw_name:
        return fallback
    return raw_name if raw_name.startswith("@") else f"@{raw_name}"


async def _upsert_social_account(
    *,
    db: AsyncSession,
    user_id: uuid.UUID,
    platform: Platform,
    account_id: str,
    account_name: str,
    access_token: str,
    refresh_token: str = "",
    followers_count: int = 0,
) -> SocialAccount:
    result = await db.execute(
        select(SocialAccount).where(
            SocialAccount.platform == platform,
            SocialAccount.account_id == account_id,
        )
    )
    account = result.scalar_one_or_none()
    if account is None:
        account = SocialAccount(
            id=uuid.uuid4(),
            user_id=user_id,
            platform=platform,
            account_id=account_id,
            account_name=account_name,
            access_token=access_token,
            refresh_token=refresh_token,
            followers_count=followers_count,
        )
        db.add(account)
        return account

    account.user_id       = user_id
    account.account_name  = account_name
    account.access_token  = access_token
    account.refresh_token = refresh_token
    account.followers_count = followers_count
    return account


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #
@router.get("/tiktok/login")
async def tiktok_login(current_user: User = Depends(get_current_user)):
    """Generate TikTok OAuth 2.0 authorization URL."""
    if not TIKTOK_CLIENT_KEY or not TIKTOK_CLIENT_SECRET:
        raise HTTPException(500, "TikTok OAuth is not configured in environment variables")

    _cleanup_state_store()
    state         = secrets.token_urlsafe(24)
    code_verifier = secrets.token_urlsafe(64)

    _oauth_state_store[state] = {
        "user_id":      str(current_user.id),
        "code_verifier": code_verifier,
        "expires_at":   time.time() + 600,
    }

    auth_url = TIKTOK_AUTH_URL + "?" + urlencode({
        "client_key":            TIKTOK_CLIENT_KEY,
        "response_type":         "code",
        "scope":                 SCOPES,
        "redirect_uri":          TIKTOK_REDIRECT_URI,
        "state":                 state,
        "code_challenge":        _build_code_challenge(code_verifier),
        "code_challenge_method": "S256",
    })
    return {"auth_url": auth_url}


@router.get("/tiktok/callback")
async def tiktok_callback(
    code:              str | None = Query(default=None),
    state:             str | None = Query(default=None),
    error:             str | None = Query(default=None),
    error_description: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Handle TikTok OAuth callback — exchange code for tokens."""
    if error:
        params = {"error": error_description or error, "platform": "tiktok"}
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?{urlencode(params)}")

    if not code or not state:
        raise HTTPException(400, "Missing OAuth callback parameters")

    _cleanup_state_store()
    state_data = _oauth_state_store.pop(state, None)
    if not state_data:
        raise HTTPException(400, "OAuth state is missing or expired")

    user_id       = state_data.get("user_id")
    code_verifier = state_data.get("code_verifier")
    if not user_id or not code_verifier:
        raise HTTPException(400, "OAuth state is invalid")

    user_result = await db.execute(select(User).where(User.id == uuid.UUID(str(user_id))))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")

    # Exchange code → tokens
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            TIKTOK_TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "client_key":     TIKTOK_CLIENT_KEY,
                "client_secret":  TIKTOK_CLIENT_SECRET,
                "code":           code,
                "grant_type":     "authorization_code",
                "redirect_uri":   TIKTOK_REDIRECT_URI,
                "code_verifier":  str(code_verifier),
            },
        )
        token_data = resp.json()

    if resp.status_code >= 400 or token_data.get("error"):
        params = {
            "error":    token_data.get("error_description") or token_data.get("error") or "TikTok token exchange failed",
            "platform": "tiktok",
        }
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?{urlencode(params)}")

    access_token  = token_data["access_token"]
    refresh_token = token_data.get("refresh_token", "")
    open_id       = token_data.get("open_id", "")

    # Fetch user profile
    svc = TikTokGraphService(access_token)
    try:
        profile = await svc.get_user_info()
    finally:
        await svc.close()

    account_name     = _format_tiktok_account_name(profile, open_id)
    followers_count  = profile.get("follower_count", 0)
    account_id       = profile.get("open_id") or open_id

    await _upsert_social_account(
        db=db,
        user_id=user.id,
        platform=Platform.TIKTOK,
        account_id=account_id,
        account_name=account_name,
        access_token=access_token,
        refresh_token=refresh_token,
        followers_count=followers_count,
    )
    await db.flush()

    return RedirectResponse(
        url=f"{FRONTEND_URL}/accounts?{urlencode({'connected': 1, 'platform': 'tiktok'})}"
    )


@router.post("/tiktok/refresh/{account_id}")
async def refresh_tiktok_token(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Refresh the TikTok access token using the refresh token."""
    result = await db.execute(
        select(SocialAccount).where(
            SocialAccount.id == uuid.UUID(account_id),
            SocialAccount.user_id == current_user.id,
            SocialAccount.platform == Platform.TIKTOK,
        )
    )
    account = result.scalar_one_or_none()
    if not account or not account.refresh_token:
        raise HTTPException(404, "TikTok account or refresh token not found")

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            TIKTOK_TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "client_key":    TIKTOK_CLIENT_KEY,
                "client_secret": TIKTOK_CLIENT_SECRET,
                "grant_type":    "refresh_token",
                "refresh_token": account.refresh_token,
            },
        )
        token_data = resp.json()

    if resp.status_code >= 400 or token_data.get("error"):
        raise HTTPException(400, f"Token refresh failed: {token_data.get('error_description', token_data.get('error'))}")

    account.access_token  = token_data["access_token"]
    account.refresh_token = token_data.get("refresh_token", account.refresh_token)
    await db.flush()

    return {"status": "ok", "message": "TikTok token refreshed successfully"}


@router.post("/tiktok/sync/{account_id}")
async def sync_tiktok_data(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sync recent TikTok videos and account metrics."""
    result = await db.execute(
        select(SocialAccount).where(
            SocialAccount.id == uuid.UUID(account_id),
            SocialAccount.user_id == current_user.id,
            SocialAccount.platform == Platform.TIKTOK,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "TikTok account not found")

    svc = TikTokGraphService(account.access_token)
    synced_posts = 0
    metrics = {}

    try:
        videos = await svc.get_user_videos(max_count=20)
        for video in videos:
            existing = await db.execute(
                select(Post).where(
                    Post.account_id == account.id,
                    Post.platform_post_id == video.get("id"),
                )
            )
            if existing.scalar_one_or_none():
                continue

            post = Post(
                id=uuid.uuid4(),
                account_id=account.id,
                content_type=ContentType.IMAGE,  # TikTok = video
                status=PostStatus.PUBLISHED,
                caption=video.get("video_description") or video.get("title", ""),
                hashtags=[],
                media_urls=[video.get("cover_image_url", "")],
                published_at=video.get("create_time"),
                platform_post_id=video.get("id"),
                likes_count=video.get("like_count", 0),
                comments_count=video.get("comment_count", 0),
                shares_count=video.get("share_count", 0),
                impressions=video.get("view_count", 0),
                engagement_rate=round(
                    (video.get("like_count", 0) + video.get("comment_count", 0) + video.get("share_count", 0))
                    / max(video.get("view_count", 1), 1) * 100,
                    2,
                ),
            )
            db.add(post)
            synced_posts += 1

        metrics = await svc.get_account_metrics()
        account.followers_count = metrics.get("followers_count", account.followers_count)

        db.add(AccountMetric(
            id=uuid.uuid4(),
            account_id=account.id,
            timestamp=time.time(),
            followers_count=metrics.get("followers_count", 0),
            following_count=metrics.get("following_count", 0),
            posts_count=metrics.get("video_count", 0),
            avg_engagement_rate=0,
            reach_24h=0,
        ))
        await db.flush()

    finally:
        await svc.close()

    return {
        "status": "ok",
        "synced_posts": synced_posts,
        "followers_count": account.followers_count,
        "metrics": metrics,
    }


@router.post("/tiktok/publish/{account_id}")
async def publish_tiktok_post(
    account_id: str,
    payload: TikTokPublishIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Publish a video to TikTok from a public URL."""
    result = await db.execute(
        select(SocialAccount).where(
            SocialAccount.id == uuid.UUID(account_id),
            SocialAccount.user_id == current_user.id,
            SocialAccount.platform == Platform.TIKTOK,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "TikTok account not found")

    if not payload.video_url or not payload.title:
        raise HTTPException(400, "video_url and title are required")

    svc = TikTokGraphService(account.access_token)
    try:
        result_data = await svc.publish_video_from_url(
            video_url=payload.video_url,
            title=payload.title,
            privacy_level=payload.privacy_level,
        )
    except Exception as exc:
        raise HTTPException(400, f"TikTok API error: {exc}")
    finally:
        await svc.close()

    return {
        "status": "published",
        "publish_id": result_data.get("publish_id"),
        "title": payload.title,
    }
