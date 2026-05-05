"""Threads OAuth routes using Threads API OAuth and graph.threads.net."""
from __future__ import annotations

import time
import uuid
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth_utils import get_current_user
from core.config import get_settings
from core.database import get_db
from models.domain import Platform, SocialAccount, User
from services.threads_graph import ThreadsGraphService

router = APIRouter()
public_router = APIRouter()
settings = get_settings()

THREADS_APP_ID = settings.threads_app_id
THREADS_APP_SECRET = settings.threads_app_secret
THREADS_REDIRECT_URI = settings.threads_redirect_uri
FRONTEND_URL = settings.frontend_url.rstrip("/")

THREADS_AUTH_URL = "https://threads.net/oauth/authorize"
THREADS_TOKEN_URL = "https://graph.threads.net/oauth/access_token"
THREADS_LONG_LIVED_TOKEN_URL = "https://graph.threads.net/access_token"
THREADS_REFRESH_TOKEN_URL = "https://graph.threads.net/refresh_access_token"
THREADS_SCOPES = "threads_basic,threads_content_publish"


async def _upsert_social_account(
    *,
    db: AsyncSession,
    user_id: uuid.UUID,
    account_id: str,
    account_name: str,
    access_token: str,
    expires_in: int | None = None,
    metadata_: dict | None = None,
) -> SocialAccount:
    result = await db.execute(
        select(SocialAccount).where(
            SocialAccount.platform == Platform.THREADS,
            SocialAccount.account_id == account_id,
        )
    )
    account = result.scalar_one_or_none()
    token_expires_at = time.time() + expires_in if expires_in else None

    if account is None:
        account = SocialAccount(
            id=uuid.uuid4(),
            user_id=user_id,
            platform=Platform.THREADS,
            account_id=account_id,
            account_name=account_name,
            access_token=access_token,
            refresh_token="",
            token_expires_at=token_expires_at,
            followers_count=0,
            metadata_=metadata_ or {},
        )
        db.add(account)
        return account

    account.user_id = user_id
    account.account_name = account_name
    account.access_token = access_token
    account.token_expires_at = token_expires_at or account.token_expires_at
    if metadata_:
        account.metadata_ = {**(account.metadata_ or {}), **metadata_}
    return account


@router.get("/threads/login")
async def threads_login(current_user: User = Depends(get_current_user)):
    if not THREADS_APP_ID or not THREADS_APP_SECRET:
        raise HTTPException(500, "Threads OAuth is not configured in environment variables")

    auth_url = THREADS_AUTH_URL + "?" + urlencode(
        {
            "client_id": THREADS_APP_ID,
            "redirect_uri": THREADS_REDIRECT_URI,
            "scope": THREADS_SCOPES,
            "response_type": "code",
            "state": f"threads:{current_user.id}",
        }
    )
    return {"auth_url": auth_url}


@router.get("/threads/callback")
@public_router.get("/auth/threads/callback")
async def threads_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    if error:
        params = {"error": error_description or error, "platform": "threads"}
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?{urlencode(params)}")

    if not code or not state:
        raise HTTPException(400, "Missing OAuth callback parameters")

    try:
        user_id = uuid.UUID(state.replace("threads:", ""))
    except ValueError:
        raise HTTPException(400, "Invalid OAuth state")

    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")

    async with httpx.AsyncClient(timeout=30) as client:
        token_resp = await client.post(
            THREADS_TOKEN_URL,
            data={
                "client_id": THREADS_APP_ID,
                "client_secret": THREADS_APP_SECRET,
                "grant_type": "authorization_code",
                "redirect_uri": THREADS_REDIRECT_URI,
                "code": code,
            },
        )
        token_data = token_resp.json()

    if token_resp.status_code >= 400 or token_data.get("error"):
        error_payload = token_data.get("error") or {}
        params = {
            "error": error_payload.get("message") or token_data.get("error_message") or "Threads token exchange failed",
            "platform": "threads",
        }
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?{urlencode(params)}")

    short_token = token_data.get("access_token")
    if not short_token:
        params = {"error": "Threads token response did not include access_token", "platform": "threads"}
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?{urlencode(params)}")

    async with httpx.AsyncClient(timeout=30) as client:
        long_resp = await client.get(
            THREADS_LONG_LIVED_TOKEN_URL,
            params={
                "grant_type": "th_exchange_token",
                "client_secret": THREADS_APP_SECRET,
                "access_token": short_token,
            },
        )
        long_data = long_resp.json()

    access_token = long_data.get("access_token", short_token)
    expires_in = long_data.get("expires_in") or token_data.get("expires_in")

    svc = ThreadsGraphService(access_token)
    try:
        profile = await svc.get_profile()
    except Exception as exc:
        params = {"error": str(exc), "platform": "threads"}
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?{urlencode(params)}")
    finally:
        await svc.close()

    account_id = str(profile.get("id") or "")
    username = str(profile.get("username") or account_id).strip()
    account_name = username if username.startswith("@") else f"@{username}"

    await _upsert_social_account(
        db=db,
        user_id=user.id,
        account_id=account_id,
        account_name=account_name,
        access_token=access_token,
        expires_in=int(expires_in) if expires_in else None,
        metadata_={
            "threads_username": username.lstrip("@"),
            "threads_profile_picture_url": profile.get("threads_profile_picture_url"),
            "threads_biography": profile.get("threads_biography"),
        },
    )
    await db.flush()

    return RedirectResponse(
        url=f"{FRONTEND_URL}/accounts?{urlencode({'connected': 1, 'platform': 'threads'})}"
    )


@router.post("/threads/refresh/{account_id}")
async def refresh_threads_token(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SocialAccount).where(
            SocialAccount.id == uuid.UUID(account_id),
            SocialAccount.user_id == current_user.id,
            SocialAccount.platform == Platform.THREADS,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "Threads account not found")

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            THREADS_REFRESH_TOKEN_URL,
            params={
                "grant_type": "th_refresh_token",
                "access_token": account.access_token,
            },
        )
        data = resp.json()

    if resp.status_code >= 400 or data.get("error"):
        message = (data.get("error") or {}).get("message") or "Threads token refresh failed"
        raise HTTPException(400, message)

    account.access_token = data["access_token"]
    expires_in = data.get("expires_in")
    if expires_in:
        account.token_expires_at = time.time() + int(expires_in)
    await db.flush()
    return {"status": "ok"}
