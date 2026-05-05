"""
Routes Instagram — auth via Facebook OAuth (flux stable).
Instagram Business se connecte via Facebook OAuth + Page Access Token.
"""
from __future__ import annotations

import uuid
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import RedirectResponse
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth_utils import get_current_user
from core.config import get_settings
from core.database import get_db
from models.domain import Platform, Post, SocialAccount, User
from services.instagram_graph import InstagramService
from services.social_account_tokens import resolve_account_access_token, resolve_account_access_tokens

router = APIRouter()
settings = get_settings()

# ✅ Utilise le Facebook App ID
INSTAGRAM_APP_ID = settings.facebook_app_id
INSTAGRAM_APP_SECRET = settings.facebook_app_secret
INSTAGRAM_REDIRECT_URI = settings.instagram_redirect_uri or settings.facebook_redirect_uri
FRONTEND_URL = settings.frontend_url.rstrip("/")

# ✅ Scopes Facebook OAuth pour Instagram
INSTAGRAM_SCOPES = ",".join([
    "public_profile",
    "pages_show_list",
    "pages_read_engagement",
    "instagram_basic",
    "instagram_content_publish",
    "instagram_manage_comments",
    "instagram_manage_messages",
    "instagram_manage_insights",
])


async def _upsert_social_account(
    *,
    db: AsyncSession,
    user_id: uuid.UUID,
    platform: Platform,
    account_id: str,
    account_name: str,
    access_token: str,
    followers_count: int = 0,
    metadata_: dict | None = None,
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
            refresh_token="",
            followers_count=followers_count,
            metadata_=metadata_ or {},
        )
        db.add(account)
        return account

    account.user_id = user_id
    account.account_name = account_name
    account.access_token = access_token
    account.followers_count = followers_count
    if metadata_:
        account.metadata_ = {**(account.metadata_ or {}), **metadata_}
    return account


async def _fetch_instagram_conversations_for_account(account: SocialAccount) -> list[dict]:
    instagram_account_id = str(account.account_id or "").strip()
    candidate_ids = [instagram_account_id]
    metadata = account.metadata_ or {}
    page_id = str(metadata.get("facebook_page_id") or "").strip()
    last_error: Exception | None = None
    token_candidates = resolve_account_access_tokens(account)
    logger.info(
        "Instagram OAuth inbox fetch start account_name='{}' social_account_id='{}' account_id='{}' facebook_page_id='{}' token_sources={}",
        account.account_name,
        account.id,
        instagram_account_id,
        page_id,
        [source for _token, source in token_candidates],
    )
    if not token_candidates:
        raise ValueError(f"No access token available for Instagram account '{account.account_name}'")

    for token, token_source in token_candidates:
        svc = InstagramService(token)
        try:
            for candidate_id in candidate_ids:
                if not candidate_id:
                    continue
                try:
                    conversations = await svc.get_conversations(candidate_id)
                    logger.info(
                        "Instagram OAuth inbox candidate='{}' token_source='{}' returned {} conversation(s) for account_name='{}'",
                        candidate_id,
                        token_source,
                        len(conversations),
                        account.account_name,
                    )
                    if conversations:
                        return conversations
                    if conversations == []:
                        return []
                except Exception as exc:
                    last_error = exc
                    logger.warning(
                        "Instagram OAuth inbox candidate='{}' token_source='{}' failed for account_name='{}': {}",
                        candidate_id,
                        token_source,
                        account.account_name,
                        exc,
                    )
        finally:
            await svc.close()

    if not instagram_account_id:
        raise ValueError(
            f"Instagram account_id missing for account '{account.account_name}'"
        )
    if last_error:
        raise ValueError(
            f"{last_error} | diagnostics: instagram_account_id={instagram_account_id}, facebook_page_id={page_id}"
        )
    return []


# ══════════════════════════════════════════════════════════
# AUTH — Connexion Instagram via Facebook OAuth
# ══════════════════════════════════════════════════════════

@router.get("/instagram/login")
async def instagram_login(current_user: User = Depends(get_current_user)):
    """
    Génère l'URL OAuth Facebook avec les scopes Instagram.
    ⚠️ Dans le popup Facebook :
    - Reste sur ton compte Facebook (Sou Kaina)
    - Clique "Modifier les paramètres"
    - Coche la Page "AI Automation Studio"
    - Coche le compte Instagram @sou_kaina_2003
    - Enregistre
    """
    if not INSTAGRAM_APP_ID or not INSTAGRAM_APP_SECRET:
        raise HTTPException(500, "Instagram OAuth not configured")

    auth_url = "https://www.facebook.com/v20.0/dialog/oauth?" + urlencode({
        "client_id": INSTAGRAM_APP_ID,
        "redirect_uri": INSTAGRAM_REDIRECT_URI,
        "scope": INSTAGRAM_SCOPES,
        "response_type": "code",
        "state": f"instagram:{current_user.id}",
        "auth_type": "rerequest",
    })
    return {"auth_url": auth_url}


@router.get("/instagram/callback")
async def instagram_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_message: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    Callback OAuth Facebook — échange le code contre un token,
    puis récupère le compte Instagram Business lié aux Pages Facebook.
    """
    if error:
        params = {"error": error_message or error, "platform": "instagram"}
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?{urlencode(params)}")

    if not code or not state:
        raise HTTPException(400, "Missing OAuth parameters")

    try:
        user_id_str = state.replace("instagram:", "")
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise HTTPException(400, "Invalid state parameter")

    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")

    # ── Étape 1 : Short-lived token Facebook ──
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://graph.facebook.com/v20.0/oauth/access_token",
            params={
                "client_id": INSTAGRAM_APP_ID,
                "client_secret": INSTAGRAM_APP_SECRET,
                "redirect_uri": INSTAGRAM_REDIRECT_URI,
                "code": code,
            },
        )
        token_data = resp.json()

    print("📦 SHORT TOKEN:", token_data)

    if "error" in token_data:
        params = {"error": token_data["error"].get("message", "Token exchange failed"), "platform": "instagram"}
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?{urlencode(params)}")

    short_token = token_data["access_token"]

    # ── Étape 2 : Long-lived token (60 jours) ──
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://graph.facebook.com/v20.0/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": INSTAGRAM_APP_ID,
                "client_secret": INSTAGRAM_APP_SECRET,
                "fb_exchange_token": short_token,
            },
        )
        ll_data = resp.json()

    print("🔑 LONG TOKEN:", ll_data)
    long_token = ll_data.get("access_token", short_token)

    # ── Étape 3 : Pages Facebook avec comptes Instagram ──
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://graph.facebook.com/v20.0/me/accounts",
            params={
                "access_token": long_token,
                "fields": "id,name,access_token,instagram_business_account",
            },
        )
        pages_data = resp.json()

    print("📄 PAGES:", pages_data)

    pages = pages_data.get("data", [])
    if not pages:
        params = {
            "error": "Aucune Page Facebook trouvée. Dans le popup Facebook, cliquez 'Modifier les paramètres' et cochez votre Page AI Automation Studio.",
            "platform": "instagram",
        }
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?{urlencode(params)}")

    saved = []

    for page in pages:
        page_token = page.get("access_token", long_token)
        ig_account = page.get("instagram_business_account")

        if not ig_account:
            print(f"⚠️ Page {page.get('name')} sans Instagram")
            continue

        ig_id = ig_account["id"]
        ig_svc = InstagramService(page_token)
        try:
            ig_info = await ig_svc.get_account_info(ig_id)
            print("👤 IG INFO:", ig_info)
        finally:
            await ig_svc.close()

        if "error" in ig_info:
            print(f"❌ Erreur: {ig_info}")
            continue

        await _upsert_social_account(
            db=db,
            user_id=user.id,
            platform=Platform.INSTAGRAM,
            account_id=ig_id,
            account_name=ig_info.get("username", ig_info.get("name", "")),
            access_token=page_token,
            followers_count=ig_info.get("followers_count", 0),
            metadata_={
                "instagram_account_id": ig_id,
                "instagram_username": ig_info.get("username", ig_info.get("name", "")),
                "facebook_page_id": page.get("id"),
                "facebook_page_name": page.get("name"),
            },
        )
        saved.append(ig_info.get("username", ig_id))

    await db.flush()

    if not saved:
        params = {
            "error": "Aucun compte Instagram Business trouvé. Liez @sou_kaina_2003 à votre Page dans les paramètres Facebook.",
            "platform": "instagram",
        }
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?{urlencode(params)}")

    params = {"connected": len(saved), "platform": "instagram", "account": ",".join(saved)}
    return RedirectResponse(url=f"{FRONTEND_URL}/accounts?{urlencode(params)}")


# ══════════════════════════════════════════════════════════
# PUBLICATION
# ══════════════════════════════════════════════════════════

@router.post("/instagram/publish/image/{account_id}")
async def publish_image(
    account_id: str,
    caption: str = "",
    image: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    import base64
    account = await _get_account(account_id, user_id=current_user.id, db=db)
    image_data = await image.read()
    image_b64 = base64.b64encode(image_data).decode("utf-8")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.imgbb.com/1/upload",
            data={"key": settings.imgbb_api_key, "image": image_b64}
        )
    imgbb_data = resp.json()
    if not imgbb_data.get("success"):
        raise HTTPException(500, "Échec upload image")

    svc = InstagramService(account.access_token)
    try:
        result = await svc.publish_image_post(
            ig_user_id=account.account_id,
            image_url=imgbb_data["data"]["url"],
            caption=caption,
        )
    finally:
        await svc.close()

    if "error" in result:
        raise HTTPException(400, result["error"]["message"])
    return result


@router.post("/instagram/publish/reel/{account_id}")
async def publish_reel(
    account_id: str,
    video_url: str,
    caption: str = "",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    account = await _get_account(account_id, user_id=current_user.id, db=db)
    svc = InstagramService(account.access_token)
    try:
        result = await svc.publish_reel(ig_user_id=account.account_id, video_url=video_url, caption=caption)
    finally:
        await svc.close()
    if "error" in result:
        raise HTTPException(400, result["error"]["message"])
    return result


@router.post("/instagram/publish/story/{account_id}")
async def publish_story(
    account_id: str,
    image_url: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    account = await _get_account(account_id, user_id=current_user.id, db=db)
    svc = InstagramService(account.access_token)
    try:
        result = await svc.publish_story(ig_user_id=account.account_id, image_url=image_url)
    finally:
        await svc.close()
    if "error" in result:
        raise HTTPException(400, result["error"]["message"])
    return result


# ══════════════════════════════════════════════════════════
# LECTURE
# ══════════════════════════════════════════════════════════

@router.get("/instagram/posts/{account_id}")
async def get_posts(account_id: str, limit: int = 20, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, user_id=current_user.id, db=db)
    token, _token_source = resolve_account_access_token(account)
    svc = InstagramService(token)
    try:
        posts = await svc.get_media(account.account_id, limit=limit)
    finally:
        await svc.close()
    return {"status": "ok", "posts": posts, "total": len(posts)}


@router.get("/instagram/comments/{account_id}/{media_id}")
async def get_comments(account_id: str, media_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, user_id=current_user.id, db=db)
    token, _token_source = resolve_account_access_token(account)
    svc = InstagramService(token)
    try:
        comments = await svc.get_comments(media_id)
    finally:
        await svc.close()
    return {"status": "ok", "comments": comments, "total": len(comments)}


@router.post("/instagram/comments/{account_id}/{comment_id}/reply")
async def reply_comment(account_id: str, comment_id: str, message: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, user_id=current_user.id, db=db)
    token, _token_source = resolve_account_access_token(account)
    svc = InstagramService(token)
    try:
        result = await svc.reply_to_comment(comment_id, message)
    finally:
        await svc.close()
    return {"status": "ok", "reply": result}


@router.get("/instagram/inbox/{account_id}")
async def get_inbox(account_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, user_id=current_user.id, db=db)
    conversations = await _fetch_instagram_conversations_for_account(account)
    return {"status": "ok", "conversations": conversations, "total": len(conversations)}


@router.get("/instagram/debug/{account_id}")
async def debug_instagram_account(account_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, user_id=current_user.id, db=db)
    metadata = account.metadata_ or {}
    resolved_token, token_source = resolve_account_access_token(account)
    diagnostics = {
        "social_account_id": str(account.id),
        "platform": account.platform.value,
        "account_name": account.account_name,
        "instagram_account_id": account.account_id,
        "facebook_page_id": metadata.get("facebook_page_id"),
        "facebook_page_name": metadata.get("facebook_page_name"),
        "token_source": token_source,
        "token_prefix": (resolved_token or "")[:18],
    }
    try:
        conversations = await _fetch_instagram_conversations_for_account(account)
        diagnostics["conversation_count"] = len(conversations)
        diagnostics["sample_ids"] = [item.get("id") for item in conversations[:5]]
        diagnostics["status"] = "ok"
    except Exception as exc:
        diagnostics["status"] = "error"
        diagnostics["error"] = str(exc)
    return diagnostics


@router.post("/instagram/inbox/{account_id}/send")
async def send_dm(account_id: str, recipient_id: str, message: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, user_id=current_user.id, db=db)
    token, _token_source = resolve_account_access_token(account)
    svc = InstagramService(token)
    try:
        result = await svc.send_dm(account.account_id, recipient_id, message)
    finally:
        await svc.close()
    return {"status": "ok", "result": result}


# ══════════════════════════════════════════════════════════
# ANALYTICS
# ══════════════════════════════════════════════════════════

@router.get("/instagram/insights/{account_id}")
async def get_insights(account_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, user_id=current_user.id, db=db)
    token, _token_source = resolve_account_access_token(account)
    svc = InstagramService(token)
    try:
        insights = await svc.get_account_insights(account.account_id)
        info = await svc.get_account_info(account.account_id)
    finally:
        await svc.close()
    return {"status": "ok", "account": {"username": info.get("username"), "followers": info.get("followers_count"), "following": info.get("follows_count"), "posts": info.get("media_count")}, "insights": insights}


@router.get("/instagram/insights/{account_id}/post/{media_id}")
async def get_post_insights(account_id: str, media_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, user_id=current_user.id, db=db)
    token, _token_source = resolve_account_access_token(account)
    svc = InstagramService(token)
    try:
        insights = await svc.get_post_insights(media_id)
    finally:
        await svc.close()
    return {"status": "ok", "media_id": media_id, "insights": insights}


# ══════════════════════════════════════════════════════════
# HELPER PRIVÉ
# ══════════════════════════════════════════════════════════

async def _get_account(account_id: str, user_id: uuid.UUID, db: AsyncSession, platform: Platform = Platform.INSTAGRAM) -> SocialAccount:
    result = await db.execute(
        select(SocialAccount).where(
            SocialAccount.id == uuid.UUID(account_id),
            SocialAccount.user_id == user_id,
            SocialAccount.platform == platform,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "Instagram account not found")
    return account
