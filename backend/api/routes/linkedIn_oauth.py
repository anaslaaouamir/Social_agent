"""
Routes OAuth LinkedIn + synchronisation des données réelles.
"""
from __future__ import annotations

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
from models.domain import AccountMetric, Platform, Post, SocialAccount, User
from services.linkedIn_graph import LinkedInGraphService

router = APIRouter()
settings = get_settings()

LINKEDIN_CLIENT_ID     = settings.linkedin_client_id
LINKEDIN_CLIENT_SECRET = settings.linkedin_client_secret
LINKEDIN_REDIRECT_URI  = settings.linkedin_redirect_uri
FRONTEND_URL           = settings.frontend_url.rstrip("/")

# ─────────────────────────────────────────────────────────────────────────── #
# SCOPES                                                                       #
# ─────────────────────────────────────────────────────────────────────────── #
# openid + profile + email  → Sign In with LinkedIn (OpenID Connect)
# w_member_social           → Publier / commenter / liker en tant que membre
# r_basicprofile            → Lire le profil de base
# ─────────────────────────────────────────────────────────────────────────── #
SCOPES = " ".join([
    "openid",           # ✅ Identité OpenID Connect
    "profile",          # ✅ Nom, photo, URN du membre
    "email",            # ✅ Adresse e-mail
    "w_member_social",  # ✅ Publier posts, commentaires, likes
])


# ─────────────────────────────────────────────────────────────────────────── #
# Helper upsert — identique à Facebook                                         #
# ─────────────────────────────────────────────────────────────────────────── #
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
            SocialAccount.platform   == platform,
            SocialAccount.account_id == account_id,
        )
    )
    account = result.scalar_one_or_none()
    if account is None:
        account = SocialAccount(
            id             = uuid.uuid4(),
            user_id        = user_id,
            platform       = platform,
            account_id     = account_id,
            account_name   = account_name,
            access_token   = access_token,
            refresh_token  = refresh_token,
            followers_count= followers_count,
        )
        db.add(account)
        return account

    account.user_id        = user_id
    account.account_name   = account_name
    account.access_token   = access_token
    account.refresh_token  = refresh_token
    account.followers_count= followers_count
    return account


# ─────────────────────────────────────────────────────────────────────────── #
# STEP 1 — Générer l'URL d'autorisation LinkedIn                               #
# ─────────────────────────────────────────────────────────────────────────── #
@router.get("/linkedin/login")
async def linkedin_login(current_user: User = Depends(get_current_user)):
    """
    Génère l'URL d'autorisation LinkedIn OAuth 2.0 (3-legged).
    Le frontend redirige le navigateur vers cette URL.
    """
    if not LINKEDIN_CLIENT_ID or not LINKEDIN_CLIENT_SECRET:
        raise HTTPException(500, "LinkedIn OAuth is not configured in environment variables")

    auth_url = "https://www.linkedin.com/oauth/v2/authorization?" + urlencode({
        "response_type": "code",
        "client_id":      LINKEDIN_CLIENT_ID,
        "redirect_uri":   LINKEDIN_REDIRECT_URI,
        "scope":          SCOPES,
        "state":          str(current_user.id),  # anti-CSRF : user_id
    })
    return {"auth_url": auth_url}


# ─────────────────────────────────────────────────────────────────────────── #
# STEP 2 — Callback LinkedIn                                                   #
# ─────────────────────────────────────────────────────────────────────────── #
@router.get("/linkedin/callback")
async def linkedin_callback(
    code:          str | None = Query(default=None),
    state:         str | None = Query(default=None),
    error:         str | None = Query(default=None),
    error_description: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    LinkedIn redirige ici avec un code OAuth.
    On l'échange contre un access_token, puis on récupère
    le profil du membre et on sauvegarde le compte.
    """
    # ── Erreur retournée par LinkedIn ──────────────────────────────────────
    if error:
        params = {"error": error_description or error, "platform": "linkedin"}
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?{urlencode(params)}")

    if not code or not state:
        raise HTTPException(400, "Missing OAuth callback parameters")

    # ── Retrouver l'utilisateur via state ──────────────────────────────────
    user_result = await db.execute(select(User).where(User.id == uuid.UUID(state)))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")

    # ── Échanger le code contre un access_token ────────────────────────────
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://www.linkedin.com/oauth/v2/accessToken",
            data={
                "grant_type":    "authorization_code",
                "code":          code,
                "redirect_uri":  LINKEDIN_REDIRECT_URI,
                "client_id":     LINKEDIN_CLIENT_ID,
                "client_secret": LINKEDIN_CLIENT_SECRET,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        token_data = resp.json()

    if "error" in token_data:
        params = {
            "error": f"OAuth error: {token_data.get('error_description', token_data['error'])}",
            "platform": "linkedin",
        }
        return RedirectResponse(url=f"{FRONTEND_URL}/accounts?{urlencode(params)}")

    access_token  = token_data["access_token"]
    # LinkedIn retourne un refresh_token uniquement pour certains partenaires
    refresh_token = token_data.get("refresh_token", "")

    # ── Récupérer le profil du membre ──────────────────────────────────────
    svc = LinkedInGraphService(access_token)
    try:
        profile = await svc.get_member_profile()
    finally:
        await svc.close()

    member_urn  = profile["id"]          # ex: "urn:li:person:AbCdEfG"
    member_name = profile["name"]        # "Prénom Nom"

    await _upsert_social_account(
        db             = db,
        user_id        = user.id,
        platform       = Platform.LINKEDIN,
        account_id     = member_urn,
        account_name   = member_name,
        access_token   = access_token,
        refresh_token  = refresh_token,
        followers_count= 0,
    )
    await db.flush()

    return RedirectResponse(
        url=f"{FRONTEND_URL}/accounts?{urlencode({'connected': 1, 'platform': 'linkedin'})}"
    )


# ─────────────────────────────────────────────────────────────────────────── #
# SYNC — Posts + métriques                                                     #
# ─────────────────────────────────────────────────────────────────────────── #
@router.post("/linkedin/sync/{account_id}")
async def sync_linkedin_data(
    account_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Synchronise les posts et métriques LinkedIn
    depuis l'API REST pour un compte connecté.
    """
    result = await db.execute(
        select(SocialAccount).where(
            SocialAccount.id      == uuid.UUID(account_id),
            SocialAccount.user_id == current_user.id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "Account not found")

    svc = LinkedInGraphService(account.access_token)
    synced_posts = 0
    metrics      = {}

    try:
        # ── Posts du membre ────────────────────────────────────────────────
        posts = await svc.get_member_posts(account.account_id)
        for p in posts:
            total_eng = p["likes"] + p["comments"] + p["reposts"]
            post = Post(
                id             = uuid.uuid4(),
                account_id     = account.id,
                platform       = Platform.LINKEDIN,
                external_id    = p["id"],
                content        = p.get("text", ""),
                likes_count    = p["likes"],
                comments_count = p["comments"],
                shares_count   = p["reposts"],
                engagement_rate= round(total_eng / max(account.followers_count, 1) * 100, 2),
                published_at   = p.get("created_at"),
            )
            db.add(post)
            synced_posts += 1

        # ── Métriques du profil ────────────────────────────────────────────
        metrics = await svc.get_member_analytics(account.account_id)
        account.followers_count = metrics.get("follower_count", account.followers_count)

        if metrics:
            metric_record = AccountMetric(
                id             = uuid.uuid4(),
                account_id     = account.id,
                followers_count= account.followers_count,
                reach          = metrics.get("reach", 0),
                impressions    = metrics.get("impressions", 0),
                engagement_rate= 0,
            )
            db.add(metric_record)

        await db.flush()
    finally:
        await svc.close()

    return {
        "status":       "ok",
        "synced_posts": synced_posts,
        "metrics":      metrics,
        "account": {
            "id":        str(account.id),
            "name":      account.account_name,
            "platform":  account.platform.value,
            "followers": account.followers_count,
        },
    }


# ─────────────────────────────────────────────────────────────────────────── #
# PUBLISH — Publier un post LinkedIn                                            #
# ─────────────────────────────────────────────────────────────────────────── #
@router.post("/linkedin/publish/{account_id}")
async def publish_linkedin_post(
    account_id:  str,
    message:     str,
    visibility:  str = "PUBLIC",   # "PUBLIC" | "CONNECTIONS"
    image_url:   str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Publie un post texte (ou avec image) sur le profil LinkedIn connecté.
    Nécessite : w_member_social activé dans le Developer Portal.
    """
    result = await db.execute(
        select(SocialAccount).where(
            SocialAccount.id       == uuid.UUID(account_id),
            SocialAccount.user_id  == current_user.id,
            SocialAccount.platform == Platform.LINKEDIN,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "LinkedIn account not found")

    svc = LinkedInGraphService(account.access_token)
    try:
        result_post = await svc.create_post(
            author_urn  = account.account_id,
            text        = message,
            visibility  = visibility,
            image_url   = image_url,
        )
    finally:
        await svc.close()

    return {
        "status":    "published",
        "post_id":   result_post.get("linkedin_post_id"),
        "member":    account.account_name,
        "message":   message[:100] + "..." if len(message) > 100 else message,
    }


# ─────────────────────────────────────────────────────────────────────────── #
# COMMENTS — Lire les commentaires d'un post                                   #
# ─────────────────────────────────────────────────────────────────────────── #
@router.get("/linkedin/comments/{account_id}/{post_urn}")
async def get_linkedin_post_comments(
    account_id: str,
    post_urn:   str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Récupère les commentaires d'un post LinkedIn.
    Nécessite : w_member_social (Community Management API).
    """
    result = await db.execute(
        select(SocialAccount).where(
            SocialAccount.id      == uuid.UUID(account_id),
            SocialAccount.user_id == current_user.id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "Account not found")

    svc = LinkedInGraphService(account.access_token)
    try:
        comments = await svc.get_post_comments(post_urn)
    finally:
        await svc.close()

    return {
        "status":   "ok",
        "post_urn": post_urn,
        "comments": comments,
        "total":    len(comments),
    }


# ─────────────────────────────────────────────────────────────────────────── #
# COMMENT — Poster un commentaire sur un post                                  #
# ─────────────────────────────────────────────────────────────────────────── #
@router.post("/linkedin/comments/{account_id}/{post_urn}")
async def add_linkedin_comment(
    account_id:   str,
    post_urn:     str,
    comment_text: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Poste un commentaire sur un post LinkedIn.
    Nécessite : w_member_social activé.
    """
    result = await db.execute(
        select(SocialAccount).where(
            SocialAccount.id      == uuid.UUID(account_id),
            SocialAccount.user_id == current_user.id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "Account not found")

    svc = LinkedInGraphService(account.access_token)
    try:
        created = await svc.add_comment(
            post_urn   = post_urn,
            actor_urn  = account.account_id,
            text       = comment_text,
        )
    finally:
        await svc.close()

    return {
        "status":     "commented",
        "comment_id": created.get("comment_id"),
        "post_urn":   post_urn,
        "text":       comment_text,
    }


# ─────────────────────────────────────────────────────────────────────────── #
# ANALYTICS — Métriques d'un post spécifique                                   #
# ─────────────────────────────────────────────────────────────────────────── #
@router.get("/linkedin/analytics/{account_id}/{post_urn}")
async def get_linkedin_post_analytics(
    account_id: str,
    post_urn:   str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Retourne les métriques détaillées d'un post LinkedIn
    (impressions, clics, likes, commentaires, reposts).
    """
    result = await db.execute(
        select(SocialAccount).where(
            SocialAccount.id      == uuid.UUID(account_id),
            SocialAccount.user_id == current_user.id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "Account not found")

    svc = LinkedInGraphService(account.access_token)
    try:
        analytics = await svc.get_post_analytics(post_urn)
    finally:
        await svc.close()

    return {
        "status":    "ok",
        "post_urn":  post_urn,
        "analytics": analytics,
    }
