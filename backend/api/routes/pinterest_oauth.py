"""
Routes OAuth Pinterest + synchronisation + publication.
Uses Pinterest OAuth 2.0 with PKCE.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
import time
import uuid
from datetime import datetime
from typing import Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth_utils import get_current_user
from core.config import get_settings
from core.database import get_db
from models.domain import ContentType, Platform, Post, PostStatus, SocialAccount, User

router = APIRouter()
settings = get_settings()

PINTEREST_APP_ID = settings.pinterest_app_id
PINTEREST_APP_SECRET = settings.pinterest_app_secret
PINTEREST_REDIRECT_URI = settings.pinterest_redirect_uri
FRONTEND_URL = settings.frontend_url.rstrip("/")

PINTEREST_AUTH_URL = "https://www.pinterest.com/oauth/"
PINTEREST_TOKEN_URL = "https://api-sandbox.pinterest.com/v5/oauth/token"
PINTEREST_API_BASE = "https://api-sandbox.pinterest.com/v5"

SCOPES = "boards:read,boards:write,pins:read,pins:write,user_accounts:read,analytics:read"

_oauth_state_store: dict[str, dict[str, str | float]] = {}


class PinterestPublishIn(BaseModel):
    title: str
    board_id: str
    description: str = ""
    media_url: str = ""
    link: str = ""
    alt_text: str = ""


# ── Helpers ──────────────────────────────────────────────────────

def _cleanup_state_store() -> None:
    now = time.time()
    expired = [k for k, v in _oauth_state_store.items() if float(v.get("expires_at", 0)) <= now]
    for k in expired:
        _oauth_state_store.pop(k, None)


def _build_code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def _basic_auth_header() -> str:
    credentials = f"{PINTEREST_APP_ID}:{PINTEREST_APP_SECRET}"
    return base64.b64encode(credentials.encode()).decode()


def _parse_timestamp(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


async def _fetch_pinterest_user_info(access_token: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{PINTEREST_API_BASE}/user_account",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.status_code != 200:
            logger.error(f"Failed to fetch user info: {resp.text}")
            return {}
        data = resp.json()
    return {
        "account_id": data.get("username", ""),
        "username": data.get("username", ""),
        "display_name": data.get("profile_name", ""),
        "profile_image": data.get("profile_image", ""),
        "website": data.get("website_url", ""),
        "bio": data.get("bio", ""),
        "follower_count": data.get("follower_count", 0),
        "board_count": data.get("board_count", 0),
        "pin_count": data.get("pin_count", 0),
    }


async def _upsert_social_account(
    *, db: AsyncSession, user_id: uuid.UUID, platform: Platform,
    account_id: str, account_name: str, access_token: str,
    refresh_token: str = "", followers_count: int = 0,
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
            id=uuid.uuid4(), user_id=user_id, platform=platform,
            account_id=account_id, account_name=account_name,
            access_token=access_token, refresh_token=refresh_token,
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


# ── OAuth: Login ────────────────────────────────────────────────

@router.get("/pinterest/login")
async def pinterest_login(current_user: User = Depends(get_current_user)):
    """Generate Pinterest OAuth 2.0 authorization URL with PKCE."""
    if not PINTEREST_APP_ID or not PINTEREST_APP_SECRET:
        raise HTTPException(500, "Pinterest OAuth not configured (missing APP_ID or APP_SECRET)")

    _cleanup_state_store()
    state = secrets.token_urlsafe(24)
    code_verifier = secrets.token_urlsafe(64)
    _oauth_state_store[state] = {
        "user_id": str(current_user.id),
        "code_verifier": code_verifier,
        "expires_at": time.time() + 600,
    }

    auth_url = PINTEREST_AUTH_URL + "?" + urlencode({
        "client_id": PINTEREST_APP_ID,
        "response_type": "code",
        "scope": SCOPES,
        "redirect_uri": PINTEREST_REDIRECT_URI,
        "state": state,
        "code_challenge": _build_code_challenge(code_verifier),
        "code_challenge_method": "S256",
    })
    return {"auth_url": auth_url}


# ── OAuth: Callback ─────────────────────────────────────────────

@router.get("/pinterest/callback")
async def pinterest_callback(
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
    error_description: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Handle Pinterest OAuth callback — NO auth required."""
    if error:
        logger.error(f"Pinterest OAuth error: {error_description or error}")
        params = {"error": error_description or error, "platform": "pinterest"}
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?{urlencode(params)}")

    if not code or not state:
        raise HTTPException(400, "Missing OAuth callback parameters (code, state)")

    _cleanup_state_store()
    state_data = _oauth_state_store.pop(state, None)
    if not state_data:
        raise HTTPException(400, "OAuth state is missing or expired")

    user_id = state_data.get("user_id")
    code_verifier = state_data.get("code_verifier")
    if not user_id or not code_verifier:
        raise HTTPException(400, "OAuth state is invalid")

    # Verify user exists
    user_result = await db.execute(select(User).where(User.id == uuid.UUID(str(user_id))))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")

    # Exchange code for tokens
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            PINTEREST_TOKEN_URL,
            headers={
                "Authorization": f"Basic {_basic_auth_header()}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": PINTEREST_REDIRECT_URI,
                "code_verifier": str(code_verifier),
            },
        )
        token_data = resp.json()

    logger.info(f"Pinterest token exchange: status={resp.status_code}, response={token_data}")

    if resp.status_code >= 400 or token_data.get("error"):
        detail = token_data.get("error_description") or token_data.get("error") or "Token exchange failed"
        logger.error(f"Pinterest token exchange failed: {detail}")
        params = {"error": detail, "platform": "pinterest"}
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?{urlencode(params)}")

    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token", "")

    # Fetch user profile from Pinterest
    profile = await _fetch_pinterest_user_info(access_token)
    logger.info(f"Pinterest profile fetched: {profile}")

    account_name = profile.get("display_name") or profile.get("username") or ""
    account_id = str(profile.get("account_id", "")) or ""

    # Save to database
    await _upsert_social_account(
        db=db, user_id=user.id, platform=Platform.PINTEREST,
        account_id=account_id, account_name=account_name,
        access_token=access_token, refresh_token=refresh_token,
        followers_count=profile.get("follower_count", 0),
    )
    await db.commit()

    return RedirectResponse(
        url=f"{FRONTEND_URL}/accounts?{urlencode({'connected': '1', 'platform': 'pinterest'})}"
    )


# ── OAuth: Refresh Token ─────────────────────────────────────────

@router.post("/pinterest/refresh/{account_id}")
async def refresh_pinterest_token(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Refresh the Pinterest access token."""
    result = await db.execute(
        select(SocialAccount).where(
            SocialAccount.id == uuid.UUID(account_id),
            SocialAccount.user_id == current_user.id,
            SocialAccount.platform == Platform.PINTEREST,
        )
    )
    account = result.scalar_one_or_none()
    if not account or not account.refresh_token:
        raise HTTPException(404, "Pinterest account or refresh token not found")

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            PINTEREST_TOKEN_URL,
            headers={
                "Authorization": f"Basic {_basic_auth_header()}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "refresh_token",
                "refresh_token": account.refresh_token,
            },
        )
        token_data = resp.json()

    if resp.status_code >= 400 or token_data.get("error"):
        raise HTTPException(400, f"Token refresh failed: {token_data.get('error_description', token_data.get('error'))}")

    account.access_token = token_data["access_token"]
    account.refresh_token = token_data.get("refresh_token", account.refresh_token)
    await db.commit()
    return {"status": "ok", "message": "Pinterest token refreshed successfully"}


# ── Sync Pins ────────────────────────────────────────────────────

@router.post("/pinterest/sync/{account_id}")
async def sync_pinterest_data(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sync recent Pinterest pins and boards."""
    result = await db.execute(
        select(SocialAccount).where(
            SocialAccount.id == uuid.UUID(account_id),
            SocialAccount.user_id == current_user.id,
            SocialAccount.platform == Platform.PINTEREST,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "Pinterest account not found")

    synced_posts = 0
    boards_synced = 0

    async with httpx.AsyncClient(timeout=30) as client:
        # Fetch boards
        resp = await client.get(
            f"{PINTEREST_API_BASE}/boards",
            headers={"Authorization": f"Bearer {account.access_token}"},
            params={"page_size": 100},
        )
        if resp.status_code != 200:
            raise HTTPException(400, f"Failed to list boards: {resp.text}")
        boards = resp.json().get("items", [])
        boards_synced = len(boards)

        # Fetch pins from each board
        for board in boards:
            board_id = board.get("id", "")
            resp = await client.get(
                f"{PINTEREST_API_BASE}/boards/{board_id}/pins",
                headers={"Authorization": f"Bearer {account.access_token}"},
                params={"page_size": 100},
            )
            if resp.status_code != 200:
                continue
            pins = resp.json().get("items", [])

            for pin in pins:
                existing = await db.execute(
                    select(Post).where(
                        Post.account_id == account.id,
                        Post.platform_post_id == pin.get("id"),
                    )
                )
                if existing.scalar_one_or_none():
                    continue

                media_url = ""
                media = pin.get("media", {})
                if media:
                    images = media.get("images", {})
                    originals = images.get("originals", {})
                    media_url = originals.get("url", "")

                post = Post(
                    id=uuid.uuid4(), account_id=account.id,
                    content_type=ContentType.IMAGE, status=PostStatus.PUBLISHED,
                    caption=pin.get("title", "") or pin.get("description", ""),
                    hashtags=[], media_urls=[media_url] if media_url else [],
                    published_at=_parse_timestamp(pin.get("created_at")),
                    platform_post_id=pin.get("id"),
                )
                db.add(post)
                synced_posts += 1

    await db.commit()
    return {"status": "ok", "synced_posts": synced_posts, "boards_synced": boards_synced}


# ── Publish Pin ──────────────────────────────────────────────────

@router.post("/pinterest/publish/{account_id}")
async def publish_pinterest_pin(
    account_id: str,
    payload: PinterestPublishIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create and publish a pin on Pinterest."""
    result = await db.execute(
        select(SocialAccount).where(
            SocialAccount.id == uuid.UUID(account_id),
            SocialAccount.user_id == current_user.id,
            SocialAccount.platform == Platform.PINTEREST,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "Pinterest account not found")
    if not payload.board_id or not payload.title:
        raise HTTPException(400, "board_id and title are required")

    pin_data = {
        "title": payload.title,
        "board_id": payload.board_id,
    }
    if payload.description:
        pin_data["description"] = payload.description
    if payload.link:
        pin_data["link"] = payload.link
    if payload.alt_text:
        pin_data["alt_text"] = payload.alt_text
    if payload.media_url:
        pin_data["media_source"] = {"source_type": "image_url", "url": payload.media_url}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{PINTEREST_API_BASE}/pins",
            headers={
                "Authorization": f"Bearer {account.access_token}",
                "Content-Type": "application/json",
            },
            json=pin_data,
        )
        if resp.status_code != 201:
            raise HTTPException(400, f"Failed to create pin: {resp.text}")
        result_data = resp.json()

    post = Post(
        id=uuid.uuid4(), account_id=account.id,
        content_type=ContentType.IMAGE, status=PostStatus.PUBLISHED,
        caption=payload.title, hashtags=[],
        media_urls=[payload.media_url] if payload.media_url else [],
        published_at=time.time(), platform_post_id=result_data.get("id", ""),
    )
    db.add(post)
    await db.commit()

    return {"status": "ok", "pin_id": result_data.get("id", ""), "message": "Pin published successfully"}