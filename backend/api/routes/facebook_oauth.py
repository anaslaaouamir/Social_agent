"""
Routes OAuth Facebook + synchronisation des donnees reelles.
"""
from __future__ import annotations

import uuid
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth_utils import get_current_user
from core.config import get_settings
from core.database import get_db
from models.domain import AccountMetric, Platform, Post, SocialAccount, User
from services.facebook_graph import FacebookGraphService

router = APIRouter()
settings = get_settings()

FACEBOOK_APP_ID = settings.facebook_app_id
FACEBOOK_APP_SECRET = settings.facebook_app_secret
FACEBOOK_REDIRECT_URI = settings.facebook_redirect_uri
FRONTEND_URL = settings.frontend_url.rstrip("/")

# ✅ SCOPES CORRIGES - compatibles Facebook Login for Business
# Pour débloquer pages_manage_posts et pages_messaging :
# → Dashboard Meta → Cas d'utilisation → Ajouter chaque permission manuellement
SCOPES = ",".join(
    [
        "public_profile",            # ✅ Infos de base de l'utilisateur
        "pages_show_list",           # ✅ Lister les pages de l'utilisateur
        "pages_read_engagement",     # ✅ Lire posts, likes, commentaires
        "pages_manage_posts",        # ✅ Publier sur la page (activer dans Cas d'utilisation)
        "pages_manage_metadata",     # ✅ Lire les infos de la page
        "pages_messaging",           # ✅ Lire et envoyer des DMs (activer dans Cas d'utilisation)
        "pages_read_user_content",   # ✅ Lire les commentaires des utilisateurs sur la page
        "business_management",       # ✅ 
    ]
)


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


@router.get("/facebook/login")
async def facebook_login(current_user: User = Depends(get_current_user)):
    """
    Genere l'URL d'autorisation Meta OAuth.
    Le frontend redirige ensuite le navigateur vers cette URL.
    """
    if not FACEBOOK_APP_ID or not FACEBOOK_APP_SECRET:
        raise HTTPException(500, "Facebook OAuth is not configured in environment variables")

    auth_url = "https://www.facebook.com/v20.0/dialog/oauth?" + urlencode(
        {
            "client_id": FACEBOOK_APP_ID,
            "redirect_uri": FACEBOOK_REDIRECT_URI,
            "scope": SCOPES,
            "state": str(current_user.id),
            "response_type": "code",
            "auth_type": "rerequest",
        }
    )
    return {"auth_url": auth_url}


@router.get("/facebook/callback")
async def facebook_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_message: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    Meta redirige ici avec un code OAuth.
    On l'echange contre un token puis on recupere les Pages Facebook
    et le compte Instagram Business lie quand il existe.
    """
    import httpx

    if error:
        params = {"error": error_message or error, "platform": "facebook"}
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?{urlencode(params)}")

    if not code or not state:
        raise HTTPException(400, "Missing OAuth callback parameters")

    clean_state = state.replace("instagram:", "").replace("facebook:", "")
    user_result = await db.execute(select(User).where(User.id == uuid.UUID(clean_state)))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://graph.facebook.com/v20.0/oauth/access_token",
            params={
                "client_id": FACEBOOK_APP_ID,
                "client_secret": FACEBOOK_APP_SECRET,
                "redirect_uri": FACEBOOK_REDIRECT_URI,
                "code": code,
            },
        )
        token_data = resp.json()

    if "error" in token_data:
        params = {
            "error": f"OAuth error: {token_data['error']['message']}",
            "platform": "facebook",
        }
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?{urlencode(params)}")

    short_token = token_data["access_token"]
    svc = FacebookGraphService(short_token)

    try:
        ll_data = await svc.exchange_for_long_lived_token(
            short_token,
            FACEBOOK_APP_ID,
            FACEBOOK_APP_SECRET,
        )
        long_token = ll_data.get("access_token", short_token)
    finally:
        await svc.close()

    svc2 = FacebookGraphService(long_token)
    try:
        pages = await svc2.get_user_pages()
        saved = []

        if not pages:
            params = {
                "error": "Connexion Facebook reussie, mais aucune Page admin n'a ete retournee par Meta. Cliquez sur Modifier les parametres et autorisez au moins une Page Facebook.",
                "platform": "facebook",
            }
            return RedirectResponse(url=f"{FRONTEND_URL}/accounts?{urlencode(params)}")

        for page in pages:
            page_token = page.get("access_token", long_token)
            await _upsert_social_account(
                db=db,
                user_id=user.id,
                platform=Platform.FACEBOOK,
                account_id=page["id"],
                account_name=page["name"],
                access_token=page_token,
                followers_count=page.get("followers_count") or page.get("fan_count", 0),
            )
            saved.append({"platform": "facebook", "name": page["name"]})

            ig = await svc2.get_instagram_account(page["id"], page_token)
            if ig:
                await _upsert_social_account(
                    db=db,
                    user_id=user.id,
                    platform=Platform.INSTAGRAM,
                    account_id=ig["id"],
                    account_name=ig.get("username", ig.get("name", "")),
                    access_token=page_token,
                    followers_count=ig.get("followers_count", 0),
                    metadata_={
                        "instagram_account_id": ig["id"],
                        "instagram_username": ig.get("username", ig.get("name", "")),
                        "facebook_page_id": page["id"],
                        "facebook_page_name": page["name"],
                    },
                )
                saved.append({"platform": "instagram", "name": ig.get("username", "")})

        await db.flush()
    finally:
        await svc2.close()

    return RedirectResponse(
        url=f"{FRONTEND_URL}/accounts?{urlencode({'connected': len(saved), 'platform': 'facebook'})}"
    )


@router.post("/facebook/sync/{account_id}")
async def sync_facebook_data(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Synchronise les vrais posts, commentaires, DMs et metriques
    depuis l'API Graph pour un compte connecte.
    """
    result = await db.execute(
        select(SocialAccount).where(
            SocialAccount.id == uuid.UUID(account_id),
            SocialAccount.user_id == current_user.id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "Account not found")

    svc = FacebookGraphService(account.access_token)
    synced_posts = 0
    metrics = {}

    try:
        if account.platform == Platform.FACEBOOK:
            # ✅ Sync posts
            posts = await svc.get_page_posts(account.account_id, account.access_token)
            for p in posts:
                total_eng = p["likes"] + p["comments"] + p["shares"]
                post = Post(
                    id=uuid.uuid4(),
                    account_id=account.id,
                    platform_post_id=p["id"],
                    caption=p["message"][:2000] if p["message"] else "",
                    status="published",
                    content_type="image",
                    likes_count=p["likes"],
                    comments_count=p["comments"],
                    reach=0,
                    engagement_rate=round(total_eng / max(account.followers_count, 1) * 100, 2),
                    published_at=p["created_time"],
                )
                db.add(post)
                synced_posts += 1

            # ✅ Sync métriques
            metrics = await svc.get_page_insights(account.account_id, account.access_token)

        elif account.platform == Platform.INSTAGRAM:
            media_items = await svc.get_instagram_media(account.account_id, account.access_token)
            for m in media_items:
                total_eng = m.get("like_count", 0) + m.get("comments_count", 0)
                post = Post(
                    id=uuid.uuid4(),
                    account_id=account.id,
                    platform_post_id=m["id"],
                    caption=m.get("caption", "")[:2000],
                    status="published",
                    content_type=m.get("media_type", "IMAGE").lower(),
                    likes_count=m.get("like_count", 0),
                    comments_count=m.get("comments_count", 0),
                    reach=0,
                    engagement_rate=round(total_eng / max(account.followers_count, 1) * 100, 2),
                    published_at=m.get("timestamp"),
                )
                db.add(post)
                synced_posts += 1

            metrics = await svc.get_instagram_insights(account.account_id, account.access_token)
            account.followers_count = metrics.get("follower_count", account.followers_count)

        if metrics:
            metric_record = AccountMetric(
                id=uuid.uuid4(),
                account_id=account.id,
                followers_count=account.followers_count,
                reach=metrics.get("reach", 0) or metrics.get("page_reach", 0),
                impressions=metrics.get("impressions", 0) or metrics.get("page_impressions", 0),
                engagement_rate=0,
            )
            db.add(metric_record)

        await db.flush()
    finally:
        await svc.close()

    return {
        "status": "ok",
        "synced_posts": synced_posts,
        "metrics": metrics,
        "account": {
            "id": str(account.id),
            "name": account.account_name,
            "platform": account.platform.value,
            "followers": account.followers_count,
        },
    }


# ✅ NOUVEAU — Publier un post sur une Page Facebook
@router.post("/facebook/publish/{account_id}")
async def publish_facebook_post(
    account_id: str,
    message: str,
    image_url: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Publie un post texte ou image sur une Page Facebook connectée.
    Nécessite : pages_manage_posts activé dans le dashboard Meta.
    """
    import httpx

    result = await db.execute(
        select(SocialAccount).where(
            SocialAccount.id == uuid.UUID(account_id),
            SocialAccount.user_id == current_user.id,
            SocialAccount.platform == Platform.FACEBOOK,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "Facebook Page account not found")

    page_id = account.account_id
    page_token = account.access_token

    async with httpx.AsyncClient() as client:
        if image_url:
            # Post avec image
            resp = await client.post(
                f"https://graph.facebook.com/v20.0/{page_id}/photos",
                params={"access_token": page_token},
                json={"url": image_url, "caption": message},
            )
        else:
            # Post texte uniquement
            resp = await client.post(
                f"https://graph.facebook.com/v20.0/{page_id}/feed",
                params={"access_token": page_token},
                json={"message": message},
            )

    data = resp.json()

    if "error" in data:
        raise HTTPException(400, f"Facebook API error: {data['error']['message']}")

    return {
        "status": "published",
        "post_id": data.get("id"),
        "page": account.account_name,
        "message": message[:100] + "..." if len(message) > 100 else message,
    }


@router.post("/facebook/publish-with-file/{account_id}")
async def publish_with_image_file(
    account_id: str,
    message: str,
    image: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Publie un post Facebook avec image envoyee directement en multipart/form-data.
    """
    import httpx

    result = await db.execute(
        select(SocialAccount).where(
            SocialAccount.id == uuid.UUID(account_id),
            SocialAccount.user_id == current_user.id,
            SocialAccount.platform == Platform.FACEBOOK,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "Facebook Page account not found")

    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(400, "Image file is empty")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://graph.facebook.com/v20.0/{account.account_id}/photos",
            params={"access_token": account.access_token},
            data={"caption": message},
            files={
                "source": (
                    image.filename or "upload.jpg",
                    image_bytes,
                    image.content_type or "application/octet-stream",
                )
            },
        )

    data = resp.json()
    if "error" in data:
        raise HTTPException(400, f"Facebook API error: {data['error']['message']}")

    return {
        "status": "published",
        "post_id": data.get("id"),
        "page": account.account_name,
        "message": message[:100] + "..." if len(message) > 100 else message,
        "filename": image.filename,
    }


# ✅ NOUVEAU — Lire les DMs (conversations) d'une Page Facebook
@router.get("/facebook/inbox/{account_id}")
async def get_facebook_inbox(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Récupère les conversations/DMs de la Page Facebook.
    Nécessite : pages_messaging activé dans le dashboard Meta.
    """
    import httpx

    result = await db.execute(
        select(SocialAccount).where(
            SocialAccount.id == uuid.UUID(account_id),
            SocialAccount.user_id == current_user.id,
            SocialAccount.platform == Platform.FACEBOOK,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "Facebook Page account not found")

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://graph.facebook.com/v20.0/{account.account_id}/conversations",
            params={
                "access_token": account.access_token,
                "fields": "id,snippet,updated_time,message_count,unread_count,participants",
            },
        )

    data = resp.json()

    if "error" in data:
        raise HTTPException(400, f"Facebook API error: {data['error']['message']}")

    return {
        "status": "ok",
        "page": account.account_name,
        "conversations": data.get("data", []),
        "total": len(data.get("data", [])),
    }


# ✅ NOUVEAU — Lire les commentaires d'un post Facebook
@router.get("/facebook/comments/{account_id}/{post_id}")
async def get_post_comments(
    account_id: str,
    post_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Récupère tous les commentaires d'un post Facebook.
    Nécessite : pages_read_engagement activé.
    """
    import httpx

    result = await db.execute(
        select(SocialAccount).where(
            SocialAccount.id == uuid.UUID(account_id),
            SocialAccount.user_id == current_user.id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "Account not found")

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://graph.facebook.com/v20.0/{post_id}/comments",
            params={
                "access_token": account.access_token,
                "fields": "id,message,from,created_time,like_count,comment_count",
                "summary": "true",
            },
        )

    data = resp.json()

    if "error" in data:
        raise HTTPException(400, f"Facebook API error: {data['error']['message']}")

    return {
        "status": "ok",
        "post_id": post_id,
        "comments": data.get("data", []),
        "total": data.get("summary", {}).get("total_count", 0),
    }
