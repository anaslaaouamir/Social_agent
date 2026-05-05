"""
Routes OAuth Twitter/X + synchronisation + publication.
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
from services.twitter_graph import TwitterGraphService

router = APIRouter()
settings = get_settings()

TWITTER_CLIENT_ID = settings.twitter_client_id
TWITTER_CLIENT_SECRET = settings.twitter_client_secret
TWITTER_REDIRECT_URI = settings.twitter_redirect_uri
FRONTEND_URL = settings.frontend_url.rstrip("/")

TWITTER_AUTH_URL = "https://twitter.com/i/oauth2/authorize"
TWITTER_TOKEN_URL = "https://api.twitter.com/2/oauth2/token"
SCOPES = "tweet.read tweet.write users.read offline.access"

_oauth_state_store: dict[str, dict[str, str | float]] = {}


class TwitterPublishIn(BaseModel):
    text: str = ""
    media_urls: list[str] = []


def _cleanup_oauth_state_store() -> None:
    now = time.time()
    expired = [key for key, value in _oauth_state_store.items() if float(value.get("expires_at", 0)) <= now]
    for key in expired:
        _oauth_state_store.pop(key, None)


def _build_code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


def _parse_created_at(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


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

    account.user_id = user_id
    account.account_name = account_name
    account.access_token = access_token
    account.refresh_token = refresh_token
    account.followers_count = followers_count
    return account


@router.get("/twitter/login")
@router.get("/x/login")
async def twitter_login(current_user: User = Depends(get_current_user)):
    """
    Genere l'URL d'autorisation OAuth 2.0 pour X/Twitter.
    """
    if not TWITTER_CLIENT_ID or not TWITTER_CLIENT_SECRET:
        raise HTTPException(500, "Twitter OAuth is not configured in environment variables")

    _cleanup_oauth_state_store()
    state = secrets.token_urlsafe(24)
    code_verifier = secrets.token_urlsafe(64)
    _oauth_state_store[state] = {
        "user_id": str(current_user.id),
        "code_verifier": code_verifier,
        "expires_at": time.time() + 600,
    }

    auth_url = TWITTER_AUTH_URL + "?" + urlencode(
        {
            "response_type": "code",
            "client_id": TWITTER_CLIENT_ID,
            "redirect_uri": TWITTER_REDIRECT_URI,
            "scope": SCOPES,
            "state": state,
            "code_challenge": _build_code_challenge(code_verifier),
            "code_challenge_method": "S256",
        }
    )
    return {"auth_url": auth_url}


@router.get("/twitter/callback")
@router.get("/x/callback")
@router.get("/callback")
async def twitter_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    Callback OAuth X/Twitter.
    """
    if error:
        params = {"error": error_description or error, "platform": "twitter"}
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?{urlencode(params)}")

    if not code or not state:
        raise HTTPException(400, "Missing OAuth callback parameters")

    _cleanup_oauth_state_store()
    state_data = _oauth_state_store.pop(state, None)
    if not state_data:
        raise HTTPException(400, "OAuth state is missing or expired")

    user_id = state_data.get("user_id")
    code_verifier = state_data.get("code_verifier")
    if not user_id or not code_verifier:
        raise HTTPException(400, "OAuth state is invalid")

    user_result = await db.execute(select(User).where(User.id == uuid.UUID(str(user_id))))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            TWITTER_TOKEN_URL,
            auth=(TWITTER_CLIENT_ID, TWITTER_CLIENT_SECRET),
            data={
                "code": code,
                "grant_type": "authorization_code",
                "client_id": TWITTER_CLIENT_ID,
                "redirect_uri": TWITTER_REDIRECT_URI,
                "code_verifier": str(code_verifier),
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        token_data = resp.json()

    if resp.status_code >= 400 or "error" in token_data:
        params = {
            "error": token_data.get("error_description") or token_data.get("error") or "Twitter token exchange failed",
            "platform": "twitter",
        }
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?{urlencode(params)}")

    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token", "")

    svc = TwitterGraphService(access_token)
    try:
        profile = await svc.get_me()
    finally:
        await svc.close()

    public_metrics = profile.get("public_metrics", {}) or {}
    account_name = profile.get("username") or profile.get("name") or profile.get("id", "")

    await _upsert_social_account(
        db=db,
        user_id=user.id,
        platform=Platform.TWITTER,
        account_id=profile["id"],
        account_name=account_name,
        access_token=access_token,
        refresh_token=refresh_token,
        followers_count=public_metrics.get("followers_count", 0),
    )
    await db.flush()

    return RedirectResponse(
        url=f"{FRONTEND_URL}/accounts?{urlencode({'connected': 1, 'platform': 'twitter'})}"
    )


@router.post("/twitter/sync/{account_id}")
async def sync_twitter_data(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Synchronise les tweets recents et les metriques du profil X/Twitter.
    """
    result = await db.execute(
        select(SocialAccount).where(
            SocialAccount.id == uuid.UUID(account_id),
            SocialAccount.user_id == current_user.id,
            SocialAccount.platform == Platform.TWITTER,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "Twitter account not found")

    svc = TwitterGraphService(account.access_token)
    synced_posts = 0
    profile = {}

    try:
        tweets = await svc.get_user_tweets(account.account_id)
        for tweet in tweets:
            metrics = tweet.get("public_metrics", {}) or {}
            existing_result = await db.execute(
                select(Post).where(
                    Post.account_id == account.id,
                    Post.platform_post_id == tweet.get("id"),
                )
            )
            if existing_result.scalar_one_or_none():
                continue

            post = Post(
                id=uuid.uuid4(),
                account_id=account.id,
                content_type=ContentType.IMAGE,
                status=PostStatus.PUBLISHED,
                caption=tweet.get("text", ""),
                hashtags=[],
                media_urls=[],
                published_at=_parse_created_at(tweet.get("created_at")),
                platform_post_id=tweet.get("id"),
                likes_count=metrics.get("like_count", 0),
                comments_count=metrics.get("reply_count", 0),
                shares_count=metrics.get("retweet_count", 0),
                impressions=metrics.get("impression_count", 0),
                engagement_rate=round(
                    (
                        metrics.get("like_count", 0)
                        + metrics.get("reply_count", 0)
                        + metrics.get("retweet_count", 0)
                        + metrics.get("quote_count", 0)
                    ) / max(account.followers_count, 1) * 100,
                    2,
                ),
            )
            db.add(post)
            synced_posts += 1

        profile = await svc.get_user_profile(account.account_id)
        profile_metrics = profile.get("public_metrics", {}) or {}
        account.followers_count = profile_metrics.get("followers_count", account.followers_count)

        db.add(
            AccountMetric(
                id=uuid.uuid4(),
                account_id=account.id,
                timestamp=time.time(),
                followers_count=profile_metrics.get("followers_count", 0),
                following_count=profile_metrics.get("following_count", 0),
                posts_count=profile_metrics.get("tweet_count", 0),
                avg_engagement_rate=0,
                reach_24h=0,
            )
        )
        await db.flush()
    finally:
        await svc.close()

    return {
        "status": "ok",
        "synced_posts": synced_posts,
        "followers_count": account.followers_count,
        "username": profile.get("username", account.account_name),
    }


@router.post("/twitter/publish/{account_id}")
async def publish_twitter_post(
    account_id: str,
    payload: TwitterPublishIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Publie un tweet sur le compte X/Twitter connecte.
    """
    result = await db.execute(
        select(SocialAccount).where(
            SocialAccount.id == uuid.UUID(account_id),
            SocialAccount.user_id == current_user.id,
            SocialAccount.platform == Platform.TWITTER,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "Twitter account not found")

    if not payload.text.strip() and not payload.media_urls:
        raise HTTPException(400, "Tweet text or media is required")

    svc = TwitterGraphService(account.access_token)
    try:
        tweet = await svc.create_tweet_with_media(payload.text.strip(), payload.media_urls)
    except Exception as exc:
        raise HTTPException(400, f"Twitter API error: {exc}")
    finally:
        await svc.close()

    return {
        "status": "published",
        "post_id": tweet.get("id"),
        "text": tweet.get("text", payload.text.strip()[:280]),
    }
