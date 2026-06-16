"""Pinterest OAuth routes and account operations."""
from __future__ import annotations

import base64
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

router = APIRouter()
public_router = APIRouter()
settings = get_settings()

PINTEREST_APP_ID = settings.pinterest_app_id
PINTEREST_APP_SECRET = settings.pinterest_app_secret
PINTEREST_REDIRECT_URI = settings.pinterest_redirect_uri
FRONTEND_URL = settings.frontend_url.rstrip("/")

PINTEREST_AUTH_URL = "https://www.pinterest.com/oauth/"
PINTEREST_TOKEN_URL = "https://api.pinterest.com/v5/oauth/token"
PINTEREST_USER_URL = "https://api.pinterest.com/v5/user_account"

PINTEREST_SCOPES = "user_accounts:read,boards:read,boards:write,pins:read,pins:write"


async def _upsert_pinterest_account(
    *,
    db: AsyncSession,
    user_id: uuid.UUID,
    user_info: dict,
    access_token: str,
    refresh_token: str = "",
    expires_in: int | None = None,
) -> SocialAccount:
    username = str(user_info.get("username") or "pinterest_user")
    token_expires_at = time.time() + int(expires_in) if expires_in else None

    result = await db.execute(
        select(SocialAccount).where(
            SocialAccount.platform == Platform.PINTEREST,
            SocialAccount.account_id == username,
        )
    )
    account = result.scalar_one_or_none()
    metadata_ = {
        "profile_image": user_info.get("profile_image"),
        "website_url": user_info.get("website_url"),
        "account_type": user_info.get("account_type"),
    }

    if account is None:
        account = SocialAccount(
            id=uuid.uuid4(),
            user_id=user_id,
            platform=Platform.PINTEREST,
            account_id=username,
            account_name=username,
            access_token=access_token,
            refresh_token=refresh_token,
            token_expires_at=token_expires_at,
            followers_count=0,
            metadata_=metadata_,
        )
        db.add(account)
        return account

    account.user_id = user_id
    account.account_name = username
    account.access_token = access_token
    account.refresh_token = refresh_token or account.refresh_token
    account.token_expires_at = token_expires_at or account.token_expires_at
    account.metadata_ = {**(account.metadata_ or {}), **metadata_}
    return account


@router.get("/pinterest/login")
async def pinterest_login(current_user: User = Depends(get_current_user)):
    if not PINTEREST_APP_ID or not PINTEREST_APP_SECRET:
        raise HTTPException(500, "Pinterest OAuth is not configured in environment variables")

    auth_url = PINTEREST_AUTH_URL + "?" + urlencode(
        {
            "client_id": PINTEREST_APP_ID,
            "redirect_uri": PINTEREST_REDIRECT_URI,
            "response_type": "code",
            "scope": PINTEREST_SCOPES,
            "state": str(current_user.id),
        }
    )
    return {"auth_url": auth_url}


@router.get("/pinterest/callback")
@public_router.get("/auth/pinterest/callback")
async def pinterest_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    if error:
        params = {"error": error_description or error, "platform": "pinterest"}
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?{urlencode(params)}")

    if not code or not state:
        raise HTTPException(400, "Missing OAuth callback parameters")

    try:
        user_id = uuid.UUID(state)
    except ValueError:
        raise HTTPException(400, "Invalid OAuth state")

    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")

    auth_string = f"{PINTEREST_APP_ID}:{PINTEREST_APP_SECRET}"
    auth_b64 = base64.b64encode(auth_string.encode()).decode()

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            PINTEREST_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": PINTEREST_REDIRECT_URI,
            },
            headers={
                "Authorization": f"Basic {auth_b64}",
                "Content-Type": "application/x-www-form-urlencoded",
            }
        )
        token_data = resp.json()

    if resp.status_code >= 400 or token_data.get("error"):
        params = {
            "error": token_data.get("message") or token_data.get("error") or "Pinterest token exchange failed",
            "platform": "pinterest",
        }
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?{urlencode(params)}")

    access_token = token_data.get("access_token")
    if not access_token:
        params = {"error": "Pinterest token response did not include access_token", "platform": "pinterest"}
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?{urlencode(params)}")

    async with httpx.AsyncClient(timeout=30) as client:
        user_resp = await client.get(
            PINTEREST_USER_URL,
            headers={"Authorization": f"Bearer {access_token}"}
        )
        user_data = user_resp.json()

    if user_resp.status_code >= 400:
        params = {"error": user_data.get("message") or "Failed to fetch Pinterest user info", "platform": "pinterest"}
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?{urlencode(params)}")

    await _upsert_pinterest_account(
        db=db,
        user_id=user.id,
        user_info=user_data,
        access_token=access_token,
        refresh_token=token_data.get("refresh_token", ""),
        expires_in=token_data.get("expires_in"),
    )
    await db.flush()

    return RedirectResponse(url=f"{FRONTEND_URL}/accounts?{urlencode({'connected': 1, 'platform': 'pinterest'})}")
