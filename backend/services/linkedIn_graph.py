"""
LinkedIn REST API Service
Fetches real data: member profile, posts, comments, analytics.
Miroir de facebook_graph.py adapté à l'API LinkedIn v2.
"""
from __future__ import annotations

from typing import Optional
import httpx
from loguru import logger


LI_BASE    = "https://api.linkedin.com/rest"
LI_VERSION = "202604"   # Active LinkedIn-Version header (YYYYMM)


class LinkedInGraphService:
    """Wrapper autour de l'API REST LinkedIn."""

    def __init__(self, access_token: str):
        self.token  = access_token
        self.client = httpx.AsyncClient(timeout=30)

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #
    def _headers(self) -> dict:
        return {
            "Authorization":            f"Bearer {self.token}",
            "LinkedIn-Version":         LI_VERSION,
            "X-Restli-Protocol-Version":"2.0.0",
            "Content-Type":             "application/json",
        }

    def _normalize_person_urn(self, value: str) -> str:
        if not value:
            raise ValueError("LinkedIn member URN is missing")
        if value.startswith("urn:"):
            return value
        return f"urn:li:person:{value}"

    async def _get(self, path: str, params: dict | None = None) -> dict:
        url  = f"{LI_BASE}/{path.lstrip('/')}"
        resp = await self.client.get(url, headers=self._headers(), params=params or {})
        data = resp.json()
        if resp.status_code >= 400:
            raise ValueError(f"LinkedIn API error {resp.status_code}: {data}")
        return data

    async def _post(self, path: str, json: dict) -> httpx.Response:
        url  = f"{LI_BASE}/{path.lstrip('/')}"
        resp = await self.client.post(url, headers=self._headers(), json=json)
        if resp.status_code >= 400:
            raise ValueError(f"LinkedIn API error {resp.status_code}: {resp.text}")
        return resp

    async def close(self):
        await self.client.aclose()

    # ------------------------------------------------------------------ #
    # Profil membre                                                        #
    # ------------------------------------------------------------------ #
    async def get_member_profile(self) -> dict:
        """
        Retourne le profil du membre connecté via OpenID Connect.
        Scopes requis : openid profile email
        Retourne : { id, name, email, picture, sub }
        """
        # /v2/userinfo — endpoint OpenID Connect standard
        resp = await self.client.get(
            "https://api.linkedin.com/v2/userinfo",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        data = resp.json()
        if resp.status_code >= 400:
            raise ValueError(f"LinkedIn userinfo error: {data}")

        return {
            "id":      data.get("sub"),        # URN-like unique ID
            "name":    data.get("name", ""),
            "email":   data.get("email", ""),
            "picture": data.get("picture", ""),
        }

    # ------------------------------------------------------------------ #
    # Posts du membre                                                      #
    # ------------------------------------------------------------------ #
    async def get_member_posts(self, author_urn: str, count: int = 20) -> list[dict]:
        """
        Retourne les posts récents du membre.
        Scope requis : w_member_social
        """
        author_urn = self._normalize_person_urn(author_urn)
        data = await self._get(
            "posts",
            {
                "author":       author_urn,
                "q":            "author",
                "count":        count,
                "sortBy":       "LAST_MODIFIED",
            },
        )
        posts = []
        for p in data.get("elements", []):
            social = p.get("socialDetail", {})
            posts.append({
                "id":         p.get("id", ""),
                "text":       p.get("commentary", ""),
                "created_at": p.get("createdAt", ""),
                "likes":      social.get("totalSocialActivityCounts", {}).get("numLikes", 0),
                "comments":   social.get("totalSocialActivityCounts", {}).get("numComments", 0),
                "reposts":    social.get("totalSocialActivityCounts", {}).get("numShares", 0),
                "visibility": p.get("visibility", "PUBLIC"),
            })
        return posts

    # ------------------------------------------------------------------ #
    # Créer un post                                                        #
    # ------------------------------------------------------------------ #
    async def create_post(
        self,
        author_urn: str,
        text:       str,
        visibility: str = "PUBLIC",
        image_url:  str | None = None,
    ) -> dict:
        """
        Publie un post sur le profil LinkedIn du membre.
        Scope requis : w_member_social
        visibility: 'PUBLIC' | 'CONNECTIONS'
        """
        author_urn = self._normalize_person_urn(author_urn)
        body: dict = {
            "author":         author_urn,
            "commentary":     text,
            "visibility":     visibility,
            "distribution": {
                "feedDistribution":            "MAIN_FEED",
                "targetEntities":              [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState":          "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }

        # ── Post avec image ────────────────────────────────────────────
        if image_url:
            body["content"] = {
                "media": {
                    "altText": text[:100],
                    "id":      await self._upload_image(author_urn, image_url),
                }
            }

        resp = await self._post("posts", body)
        # LinkedIn retourne l'ID du post dans le header x-restli-id
        linkedin_post_id = resp.headers.get("x-restli-id", "")
        return {"linkedin_post_id": linkedin_post_id}

    async def _upload_image(self, author_urn: str, image_url: str) -> str:
        """
        Télécharge une image distante et l'upload sur LinkedIn.
        Retourne l'asset URN de l'image.
        """
        author_urn = self._normalize_person_urn(author_urn)
        # 1. Initialiser l'upload
        init_resp = await self._post(
            "images?action=initializeUpload",
            {"initializeUploadRequest": {"owner": author_urn}},
        )
        init_data      = init_resp.json()
        upload_url     = init_data["value"]["uploadUrl"]
        image_urn      = init_data["value"]["image"]

        # 2. Télécharger l'image depuis l'URL
        async with httpx.AsyncClient() as dl:
            img_resp = await dl.get(image_url)
            img_resp.raise_for_status()
            image_bytes = img_resp.content

        # 3. Uploader les bytes sur LinkedIn
        await self.client.put(
            upload_url,
            content=image_bytes,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type":  "application/octet-stream",
            },
        )
        return image_urn

    # ------------------------------------------------------------------ #
    # Commentaires                                                         #
    # ------------------------------------------------------------------ #
    async def get_post_comments(self, post_urn: str) -> list[dict]:
        """
        Retourne les commentaires d'un post LinkedIn.
        Scope requis : w_member_social
        """
        from urllib.parse import quote
        encoded_urn = quote(post_urn, safe="")
        try:
            data = await self._get(f"socialActions/{encoded_urn}/comments")
            comments = []
            for c in data.get("elements", []):
                comments.append({
                    "id":         c.get("id", ""),
                    "text":       c.get("message", {}).get("text", ""),
                    "actor":      c.get("actor", ""),
                    "created_at": c.get("created", {}).get("time", ""),
                    "likes":      c.get("likesSummary", {}).get("totalLikes", 0),
                })
            return comments
        except Exception as e:
            logger.warning(f"Could not fetch comments for post {post_urn}: {e}")
            return []

    async def add_comment(
        self,
        post_urn:  str,
        actor_urn: str,
        text:      str,
    ) -> dict:
        """
        Poste un commentaire sur un post LinkedIn.
        Scope requis : w_member_social
        """
        from urllib.parse import quote
        encoded_urn = quote(post_urn, safe="")
        resp = await self._post(
            f"socialActions/{encoded_urn}/comments",
            {
                "actor":   actor_urn,
                "message": {"text": text},
            },
        )
        comment_id = resp.headers.get("x-restli-id", "")
        return {"comment_id": comment_id}

    # ------------------------------------------------------------------ #
    # Analytics                                                            #
    # ------------------------------------------------------------------ #
    async def get_member_analytics(self, author_urn: str) -> dict:
        """
        Retourne les métriques agrégées du profil LinkedIn.
        Scope requis : r_analytics (Marketing Developer Platform)
        Fallback sur données de base si non disponible.
        """
        try:
            from urllib.parse import quote
            encoded = quote(author_urn, safe="")
            data = await self._get(
                "memberNetworkInfo",
                {"q": "member", "member": encoded},
            )
            return {
                "follower_count": data.get("followersCount", 0),
                "connections":    data.get("connectionsCount", 0),
            }
        except Exception as e:
            logger.warning(f"Analytics not available for {author_urn}: {e}")
            return {"follower_count": 0, "connections": 0}

    async def get_post_analytics(self, post_urn: str) -> dict:
        """
        Retourne les métriques d'un post LinkedIn spécifique.
        (impressions, clics, likes, commentaires, reposts)
        Scope requis : r_organization_social ou Marketing Developer Platform
        """
        try:
            from urllib.parse import quote
            encoded = quote(post_urn, safe="")
            data = await self._get(
                "organizationalEntityShareStatistics",
                {
                    "q":                      "organizationalEntity",
                    "organizationalEntity":   encoded,
                },
            )
            elements = data.get("elements", [{}])
            stats    = elements[0].get("totalShareStatistics", {}) if elements else {}
            return {
                "impressions":      stats.get("impressionCount", 0),
                "unique_impressions":stats.get("uniqueImpressionsCount", 0),
                "clicks":           stats.get("clickCount", 0),
                "likes":            stats.get("likeCount", 0),
                "comments":         stats.get("commentCount", 0),
                "reposts":          stats.get("shareCount", 0),
                "engagement_rate":  stats.get("engagement", 0.0),
            }
        except Exception as e:
            logger.warning(f"Could not fetch post analytics for {post_urn}: {e}")
            return {}

    # ------------------------------------------------------------------ #
    # Long-lived token info                                                #
    # ------------------------------------------------------------------ #
    async def get_token_introspection(self, client_id: str, client_secret: str) -> dict:
        """
        Vérifie l'état du token LinkedIn (expiration, scopes).
        Utile pour détecter les tokens expirés avant un appel.
        """
        resp = await self.client.post(
            "https://www.linkedin.com/oauth/v2/introspectToken",
            data={
                "token":         self.token,
                "client_id":     client_id,
                "client_secret": client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        return resp.json()
