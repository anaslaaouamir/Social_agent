"""YouTube OAuth routes and channel operations."""
from __future__ import annotations

import time
import uuid
from datetime import date, timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth_utils import get_current_user
from core.config import get_settings
from core.database import get_db
from models.domain import Platform, SocialAccount, User
from services.youtube_graph import YouTubeGraphService

router = APIRouter()
public_router = APIRouter()
settings = get_settings()

YOUTUBE_CLIENT_ID = settings.youtube_client_id
YOUTUBE_CLIENT_SECRET = settings.youtube_client_secret
YOUTUBE_REDIRECT_URI = settings.youtube_redirect_uri
FRONTEND_URL = settings.frontend_url.rstrip("/")

YOUTUBE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
YOUTUBE_TOKEN_URL = "https://oauth2.googleapis.com/token"

YOUTUBE_SCOPES = " ".join(
    [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/yt-analytics.readonly",
        "https://www.googleapis.com/auth/youtube.force-ssl",
        "https://www.googleapis.com/auth/youtube.readonly",
    ]
)


class YouTubeCommentIn(BaseModel):
    text: str


async def _upsert_youtube_account(
    *,
    db: AsyncSession,
    user_id: uuid.UUID,
    channel: dict,
    access_token: str,
    refresh_token: str = "",
    expires_in: int | None = None,
) -> SocialAccount:
    snippet = channel.get("snippet") or {}
    statistics = channel.get("statistics") or {}
    channel_id = str(channel.get("id") or "")
    title = str(snippet.get("title") or channel_id)
    token_expires_at = time.time() + int(expires_in) if expires_in else None

    result = await db.execute(
        select(SocialAccount).where(
            SocialAccount.platform == Platform.YOUTUBE,
            SocialAccount.account_id == channel_id,
        )
    )
    account = result.scalar_one_or_none()
    metadata_ = {
        "description": snippet.get("description"),
        "custom_url": snippet.get("customUrl"),
        "thumbnail": ((snippet.get("thumbnails") or {}).get("default") or {}).get("url"),
        "view_count": int(statistics.get("viewCount", 0) or 0),
        "video_count": int(statistics.get("videoCount", 0) or 0),
    }

    if account is None:
        account = SocialAccount(
            id=uuid.uuid4(),
            user_id=user_id,
            platform=Platform.YOUTUBE,
            account_id=channel_id,
            account_name=title,
            access_token=access_token,
            refresh_token=refresh_token,
            token_expires_at=token_expires_at,
            followers_count=int(statistics.get("subscriberCount", 0) or 0),
            metadata_=metadata_,
        )
        db.add(account)
        return account

    account.user_id = user_id
    account.account_name = title
    account.access_token = access_token
    account.refresh_token = refresh_token or account.refresh_token
    account.token_expires_at = token_expires_at or account.token_expires_at
    account.followers_count = int(statistics.get("subscriberCount", account.followers_count) or 0)
    account.metadata_ = {**(account.metadata_ or {}), **metadata_}
    return account


@router.get("/youtube/login")
async def youtube_login(current_user: User = Depends(get_current_user)):
    if not YOUTUBE_CLIENT_ID or not YOUTUBE_CLIENT_SECRET:
        raise HTTPException(500, "YouTube OAuth is not configured in environment variables")

    auth_url = YOUTUBE_AUTH_URL + "?" + urlencode(
        {
            "client_id": YOUTUBE_CLIENT_ID,
            "redirect_uri": YOUTUBE_REDIRECT_URI,
            "response_type": "code",
            "scope": YOUTUBE_SCOPES,
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": str(current_user.id),
        }
    )
    return {"auth_url": auth_url}


@router.get("/youtube/callback")
@public_router.get("/auth/youtube/callback")
async def youtube_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    if error:
        params = {"error": error_description or error, "platform": "youtube"}
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

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            YOUTUBE_TOKEN_URL,
            data={
                "client_id": YOUTUBE_CLIENT_ID,
                "client_secret": YOUTUBE_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": YOUTUBE_REDIRECT_URI,
            },
        )
        token_data = resp.json()

    if resp.status_code >= 400 or token_data.get("error"):
        params = {
            "error": token_data.get("error_description") or token_data.get("error") or "YouTube token exchange failed",
            "platform": "youtube",
        }
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?{urlencode(params)}")

    access_token = token_data.get("access_token")
    if not access_token:
        params = {"error": "YouTube token response did not include access_token", "platform": "youtube"}
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?{urlencode(params)}")

    svc = YouTubeGraphService(access_token)
    try:
        channel = await svc.get_my_channel()
    except Exception as exc:
        params = {"error": str(exc), "platform": "youtube"}
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?{urlencode(params)}")
    finally:
        await svc.close()

    await _upsert_youtube_account(
        db=db,
        user_id=user.id,
        channel=channel,
        access_token=access_token,
        refresh_token=token_data.get("refresh_token", ""),
        expires_in=token_data.get("expires_in"),
    )
    await db.flush()

    return RedirectResponse(url=f"{FRONTEND_URL}/accounts?{urlencode({'connected': 1, 'platform': 'youtube'})}")


@router.post("/youtube/refresh/{account_id}")
async def refresh_youtube_token(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SocialAccount).where(
            SocialAccount.id == uuid.UUID(account_id),
            SocialAccount.user_id == current_user.id,
            SocialAccount.platform == Platform.YOUTUBE,
        )
    )
    account = result.scalar_one_or_none()
    if not account or not account.refresh_token:
        raise HTTPException(404, "YouTube account or refresh token not found")

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            YOUTUBE_TOKEN_URL,
            data={
                "client_id": YOUTUBE_CLIENT_ID,
                "client_secret": YOUTUBE_CLIENT_SECRET,
                "grant_type": "refresh_token",
                "refresh_token": account.refresh_token,
            },
        )
        token_data = resp.json()

    if resp.status_code >= 400 or token_data.get("error"):
        raise HTTPException(400, token_data.get("error_description") or token_data.get("error") or "YouTube refresh failed")

    account.access_token = token_data["access_token"]
    if token_data.get("expires_in"):
        account.token_expires_at = time.time() + int(token_data["expires_in"])
    await db.flush()
    return {"status": "ok"}


@router.get("/youtube/videos/{account_id}")
async def list_youtube_videos(
    account_id: str,
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SocialAccount).where(
            SocialAccount.id == uuid.UUID(account_id),
            SocialAccount.user_id == current_user.id,
            SocialAccount.platform == Platform.YOUTUBE,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "YouTube account not found")

    svc = YouTubeGraphService(account.access_token)
    try:
        return {"items": await svc.get_channel_videos(account.account_id, max_results=limit)}
    finally:
        await svc.close()


@router.get("/youtube/comments/{account_id}/{video_id}")
async def list_youtube_comments(
    account_id: str,
    video_id: str,
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SocialAccount).where(
            SocialAccount.id == uuid.UUID(account_id),
            SocialAccount.user_id == current_user.id,
            SocialAccount.platform == Platform.YOUTUBE,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "YouTube account not found")

    svc = YouTubeGraphService(account.access_token)
    try:
        return {"items": await svc.get_video_comments(video_id, max_results=limit)}
    finally:
        await svc.close()


@router.post("/youtube/comments/{account_id}/{video_id}")
async def add_youtube_comment(
    account_id: str,
    video_id: str,
    payload: YouTubeCommentIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SocialAccount).where(
            SocialAccount.id == uuid.UUID(account_id),
            SocialAccount.user_id == current_user.id,
            SocialAccount.platform == Platform.YOUTUBE,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "YouTube account not found")

    svc = YouTubeGraphService(account.access_token)
    try:
        return await svc.add_comment(video_id, payload.text)
    finally:
        await svc.close()


@router.get("/youtube/analytics/{account_id}")
async def get_youtube_analytics(
    account_id: str,
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SocialAccount).where(
            SocialAccount.id == uuid.UUID(account_id),
            SocialAccount.user_id == current_user.id,
            SocialAccount.platform == Platform.YOUTUBE,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "YouTube account not found")

    end = end_date or date.today().isoformat()
    start = start_date or (date.today() - timedelta(days=30)).isoformat()
    svc = YouTubeGraphService(account.access_token)
    try:
        return await svc.get_channel_analytics(account.account_id, start, end)
    finally:
        await svc.close()


@router.post("/youtube/upload/{account_id}")
async def upload_youtube_video(
    account_id: str,
    title: str = Form(...),
    description: str = Form(""),
    privacy_status: str = Form("private"),
    tags: str = Form(""),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SocialAccount).where(
            SocialAccount.id == uuid.UUID(account_id),
            SocialAccount.user_id == current_user.id,
            SocialAccount.platform == Platform.YOUTUBE,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "YouTube account not found")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(400, "Uploaded video file is empty")

    svc = YouTubeGraphService(account.access_token)
    try:
        return await svc.upload_video(
            file_bytes=file_bytes,
            title=title,
            description=description,
            privacy_status=privacy_status,
            tags=[tag.strip() for tag in tags.split(",") if tag.strip()],
            mime_type=file.content_type or "video/mp4",
        )
    finally:
        await svc.close()
