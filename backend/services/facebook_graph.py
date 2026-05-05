"""
Facebook / Instagram Graph API Service
Fetches real data: pages, posts, insights, instagram account metrics.
Supports both classic me/accounts and Business Portfolio (owned_pages).
"""
from __future__ import annotations
import httpx
from typing import Optional
from loguru import logger


GRAPH_BASE = "https://graph.facebook.com/v20.0"


class FacebookGraphService:
    """Wrapper autour de l'API Graph Meta (Facebook + Instagram)."""

    def __init__(self, access_token: str):
        self.token = access_token
        self.client = httpx.AsyncClient(timeout=30)

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #
    async def _get(self, path: str, params: dict | None = None) -> dict:
        params = params or {}
        params["access_token"] = self.token
        url = f"{GRAPH_BASE}/{path.lstrip('/')}"
        resp = await self.client.get(url, params=params)
        data = resp.json()
        if "error" in data:
            raise ValueError(f"Graph API error: {data['error']['message']}")
        return data

    async def _post(self, path: str, *, json: dict | None = None, data: dict | None = None) -> dict:
        payload = data.copy() if data else {}
        payload["access_token"] = self.token
        url = f"{GRAPH_BASE}/{path.lstrip('/')}"
        resp = await self.client.post(url, json=json, data=payload if not json else None, params=None if not json else payload)
        data = resp.json()
        if "error" in data:
            raise ValueError(f"Graph API error: {data['error']['message']}")
        return data

    async def close(self):
        await self.client.aclose()

    # ------------------------------------------------------------------ #
    # Facebook Pages                                                       #
    # ------------------------------------------------------------------ #
    async def get_user_pages(self) -> list[dict]:
        """
        Retourne les Pages Facebook que l'utilisateur administre.
        Essaie d'abord me/accounts (admin classique),
        puis fallback sur Business Portfolio (me/businesses -> owned_pages).
        """
        # ── 1. Tentative classique ──────────────────────────────────────
        try:
            data = await self._get(
                "me/accounts",
                {"fields": "id,name,access_token,fan_count,followers_count,category"},
            )
            pages = data.get("data", [])
            if pages:
                logger.info(f"me/accounts returned {len(pages)} page(s)")
                return pages
            logger.warning("me/accounts returned empty list, trying Business Portfolio...")
        except Exception as e:
            logger.warning(f"me/accounts failed: {e}, trying Business Portfolio...")

        # ── 2. Fallback : Business Portfolio ───────────────────────────
        try:
            businesses = await self._get("me/businesses", {"fields": "id,name"})
            all_pages = []

            for biz in businesses.get("data", []):
                logger.info(f"Fetching pages for business: {biz['name']} ({biz['id']})")
                try:
                    biz_pages = await self._get(
                        f"{biz['id']}/owned_pages",
                        {"fields": "id,name,fan_count,followers_count,category"},
                    )
                    for page in biz_pages.get("data", []):
                        # Récupérer le page-scoped access token
                        try:
                            token_data = await self._get(
                                f"{page['id']}",
                                {"fields": "access_token"},
                            )
                            page["access_token"] = token_data.get("access_token", self.token)
                        except Exception as te:
                            logger.warning(f"Could not get page token for {page['id']}: {te}")
                            page["access_token"] = self.token
                        all_pages.append(page)
                except Exception as be:
                    logger.warning(f"Could not fetch pages for business {biz['id']}: {be}")

            if all_pages:
                logger.info(f"Business Portfolio returned {len(all_pages)} page(s)")
            else:
                logger.error("No pages found via Business Portfolio either.")

            return all_pages

        except Exception as e:
            logger.error(f"Business Portfolio fallback also failed: {e}")
            return []

    async def get_page_posts(self, page_id: str, page_token: str, limit: int = 25) -> list[dict]:
        """Retourne les posts d'une Page avec leurs métriques."""
        data = await self._get(
            f"{page_id}/posts",
            {
                "access_token": page_token,
                "fields": "id,message,story,created_time,full_picture,permalink_url,"
                          "reactions.summary(true),comments.summary(true),shares",
                "limit": limit,
            },
        )
        posts = []
        for p in data.get("data", []):
            posts.append({
                "id": p["id"],
                "message": p.get("message") or p.get("story", ""),
                "created_time": p.get("created_time"),
                "picture": p.get("full_picture"),
                "url": p.get("permalink_url"),
                "likes": p.get("reactions", {}).get("summary", {}).get("total_count", 0),
                "comments": p.get("comments", {}).get("summary", {}).get("total_count", 0),
                "shares": p.get("shares", {}).get("count", 0),
            })
        return posts

    async def send_page_message(self, page_id: str, recipient_id: str, message: str) -> dict:
        return await self._post(
            f"{page_id}/messages",
            json={
                "recipient": {"id": recipient_id},
                "message": {"text": message},
            },
        )

    async def add_comment(self, object_id: str, message: str) -> dict:
        return await self._post(
            f"{object_id}/comments",
            data={"message": message},
        )

    async def get_page_insights(self, page_id: str, page_token: str, days: int = 30) -> dict:
        """Retourne les insights d'une Page Facebook (reach, impressions, engagements)."""
        result = {}
        metric_candidates = [
            "page_impressions",
            "page_reach",
            "page_engaged_users",
            "page_follows",
            "page_follows_unique",
            "page_fan_adds_unique",
            "page_views_total",
        ]

        for metric in metric_candidates:
            try:
                data = await self._get(
                    f"{page_id}/insights",
                    {
                        "access_token": page_token,
                        "metric": metric,
                        "period": "day",
                        "since": f"-{days}days",
                    },
                )
            except Exception as exc:
                logger.warning("Skipping unsupported Facebook page insight '{}' for page {}: {}", metric, page_id, exc)
                continue

            for item in data.get("data", []):
                name = item["name"]
                values = item.get("values", [])
                total = sum(v.get("value", 0) for v in values if isinstance(v.get("value"), (int, float)))
                result[name] = total
        return result

    # ------------------------------------------------------------------ #
    # Instagram Business Account                                           #
    # ------------------------------------------------------------------ #
    async def get_instagram_account(self, page_id: str, page_token: str) -> Optional[dict]:
        """Récupère le compte Instagram Business lié à une Page Facebook."""
        try:
            data = await self._get(
                f"{page_id}",
                {
                    "access_token": page_token,
                    "fields": "instagram_business_account{id,name,username,biography,followers_count,"
                              "follows_count,media_count,profile_picture_url,website}",
                },
            )
            ig = data.get("instagram_business_account")
            return ig if ig else None
        except Exception as e:
            logger.warning(f"No Instagram account linked to page {page_id}: {e}")
            return None

    async def get_instagram_media(self, ig_user_id: str, page_token: str, limit: int = 25) -> list[dict]:
        """Retourne les médias Instagram avec leurs métriques."""
        data = await self._get(
            f"{ig_user_id}/media",
            {
                "access_token": page_token,
                "fields": "id,caption,media_type,media_url,thumbnail_url,timestamp,"
                          "permalink,like_count,comments_count",
                "limit": limit,
            },
        )
        return data.get("data", [])

    async def get_instagram_insights(self, ig_user_id: str, page_token: str) -> dict:
        """Retourne les insights du compte Instagram (reach, impressions, followers)."""
        metrics = "reach,impressions,follower_count,profile_views,website_clicks"
        data = await self._get(
            f"{ig_user_id}/insights",
            {
                "access_token": page_token,
                "metric": metrics,
                "period": "day",
                "since": "-30days",
            },
        )
        result = {}
        for item in data.get("data", []):
            values = item.get("values", [])
            total = sum(v.get("value", 0) for v in values if isinstance(v.get("value"), (int, float)))
            result[item["name"]] = total
        return result

    async def get_instagram_post_insights(self, media_id: str, page_token: str) -> dict:
        """Retourne les insights détaillés d'un post Instagram spécifique."""
        try:
            data = await self._get(
                f"{media_id}/insights",
                {
                    "access_token": page_token,
                    "metric": "reach,impressions,engagement,saved",
                },
            )
            result = {}
            for item in data.get("data", []):
                result[item["name"]] = item.get("values", [{}])[0].get("value", 0)
            return result
        except Exception as e:
            logger.warning(f"Could not fetch insights for media {media_id}: {e}")
            return {}

    # ------------------------------------------------------------------ #
    # Long-lived token exchange                                            #
    # ------------------------------------------------------------------ #
    async def exchange_for_long_lived_token(self, short_token: str, app_id: str, app_secret: str) -> dict:
        """Échange un token court (1h) pour un token long (60 jours)."""
        resp = await self.client.get(
            f"{GRAPH_BASE}/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": app_id,
                "client_secret": app_secret,
                "fb_exchange_token": short_token,
            },
        )
        return resp.json()
