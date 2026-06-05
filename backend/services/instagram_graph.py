"""
Service Instagram Graph API — publication, commentaires, DMs, insights.
Fonctionne via le Page Access Token Facebook lié au compte Instagram Business.
"""
from __future__ import annotations
import httpx

BASE = "https://graph.facebook.com/v20.0"


class InstagramService:
    def __init__(self, page_access_token: str):
        self.token = page_access_token
        self._client: httpx.AsyncClient | None = None

    async def _get(self, path: str, **params) -> dict:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30)
        resp = await self._client.get(
            f"{BASE}/{path}",
            params={"access_token": self.token, **params}
        )
        return resp.json()

    async def _post(self, path: str, json: dict = {}, files=None, data: dict = {}) -> dict:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30)
        if files:
            resp = await self._client.post(
                f"{BASE}/{path}",
                params={"access_token": self.token},
                files=files,
                data=data,
            )
        else:
            resp = await self._client.post(
                f"{BASE}/{path}",
                params={"access_token": self.token},
                json=json,
            )
        return resp.json()

    async def close(self):
        if self._client:
            await self._client.aclose()

    # ─────────────────────────────────────────────
    # 1. Récupérer l'ID Instagram Business lié à la Page
    # ─────────────────────────────────────────────
    async def get_ig_account_id(self, page_id: str) -> str | None:
        """
        Retourne l'ID du compte Instagram Business lié à la Page Facebook.
        Nécessite : instagram_basic
        """
        data = await self._get(
            page_id,
            fields="instagram_business_account"
        )
        ig = data.get("instagram_business_account")
        return ig["id"] if ig else None

    # ─────────────────────────────────────────────
    # 2. Infos du compte Instagram
    # ─────────────────────────────────────────────
    async def get_account_info(self, ig_user_id: str) -> dict:
        """
        Retourne les infos du compte Instagram.
        Nécessite : instagram_basic
        """
        return await self._get(
            ig_user_id,
            fields="id,username,name,biography,followers_count,follows_count,media_count,profile_picture_url,website"
        )

    # ─────────────────────────────────────────────
    # 3. Publier un post image
    # ─────────────────────────────────────────────
    async def publish_image_post(
        self,
        ig_user_id: str,
        image_url: str,         # ✅ URL publique https:// obligatoire
        caption: str = "",
    ) -> dict:
        """
        Publie une image sur Instagram.
        Nécessite : instagram_content_publish
        IMPORTANT : image_url doit être une URL publique https://
        """
        # Étape 1 : Créer le container média
        container = await self._post(
            f"{ig_user_id}/media",
            json={
                "image_url": image_url,
                "caption": caption,
            }
        )
        if "error" in container:
            return container

        creation_id = container["id"]

        # Étape 2 : Publier le container
        result = await self._post(
            f"{ig_user_id}/media_publish",
            json={"creation_id": creation_id}
        )
        return {"status": "published", "post_id": result.get("id"), "error": result.get("error")}

    # ─────────────────────────────────────────────
    # 4. Publier un Reel (vidéo)
    # ─────────────────────────────────────────────
    async def publish_reel(
        self,
        ig_user_id: str,
        video_url: str,         # ✅ URL publique https:// obligatoire
        caption: str = "",
        thumb_offset: int = 0,
    ) -> dict:
        """
        Publie un Reel Instagram.
        Nécessite : instagram_content_publish
        """
        # Étape 1 : Créer le container
        container = await self._post(
            f"{ig_user_id}/media",
            json={
                "media_type": "REELS",
                "video_url": video_url,
                "caption": caption,
                "thumb_offset": thumb_offset,
            }
        )
        if "error" in container:
            return container

        creation_id = container["id"]

        # Attendre que la vidéo soit traitée (polling)
        import asyncio
        for _ in range(10):
            await asyncio.sleep(5)
            status = await self._get(creation_id, fields="status_code")
            if status.get("status_code") == "FINISHED":
                break
            if status.get("status_code") == "ERROR":
                return {"error": "Video processing failed"}

        # Étape 2 : Publier
        result = await self._post(
            f"{ig_user_id}/media_publish",
            json={"creation_id": creation_id}
        )
        return {"status": "published", "post_id": result.get("id")}

    # ─────────────────────────────────────────────
    # 5. Publier une Story image
    # ─────────────────────────────────────────────
    async def publish_story(
        self,
        ig_user_id: str,
        image_url: str,         # ✅ URL publique https://
    ) -> dict:
        """
        Publie une Story Instagram.
        Nécessite : instagram_content_publish
        """
        container = await self._post(
            f"{ig_user_id}/media",
            json={
                "image_url": image_url,
                "media_type": "STORIES",
            }
        )
        if "error" in container:
            return container

        result = await self._post(
            f"{ig_user_id}/media_publish",
            json={"creation_id": container["id"]}
        )
        return {"status": "published", "story_id": result.get("id")}

    # ─────────────────────────────────────────────
    # 6. Lire les posts Instagram
    # ─────────────────────────────────────────────
    async def get_media(self, ig_user_id: str, limit: int = 20) -> list[dict]:
        """
        Récupère les derniers posts Instagram.
        Nécessite : instagram_basic
        """
        data = await self._get(
            f"{ig_user_id}/media",
            fields="id,caption,media_type,media_url,thumbnail_url,timestamp,like_count,comments_count,permalink",
            limit=limit,
        )
        return data.get("data", [])

    # ─────────────────────────────────────────────
    # 7. Lire les commentaires d'un post
    # ─────────────────────────────────────────────
    async def get_comments(self, media_id: str) -> list[dict]:
        """
        Récupère les commentaires d'un post Instagram.
        Nécessite : instagram_manage_comments
        """
        data = await self._get(
            f"{media_id}/comments",
            fields="id,text,username,timestamp,like_count,replies{id,text,username,timestamp,like_count}",
        )
        return data.get("data", [])

    # ─────────────────────────────────────────────
    # 8. Répondre à un commentaire
    # ─────────────────────────────────────────────
    async def reply_to_comment(self, comment_id: str, message: str) -> dict:
        """
        Répond à un commentaire Instagram.
        Nécessite : instagram_manage_comments
        """
        return await self._post(
            f"{comment_id}/replies",
            json={"message": message}
        )

    # ─────────────────────────────────────────────
    # 9. Lire les DMs (conversations)
    # ─────────────────────────────────────────────
    async def get_conversations(self, ig_user_id: str) -> list[dict]:
        """
        Récupère les conversations DM Instagram.
        Nécessite : instagram_manage_messages
        """
        data = await self._get(
            f"{ig_user_id}/conversations",
            platform="instagram",
            fields=(
                "id,updated_time,"
                "messages.limit(20){id,message,from,to,created_time}"
            ),
        )
        if "error" in data:
            message = data["error"].get("message", "Instagram conversations fetch failed")
            raise ValueError(message)
        items = data.get("data")
        if isinstance(items, list):
            return items
        nested = data.get("conversations")
        if isinstance(nested, dict):
            nested_items = nested.get("data")
            if isinstance(nested_items, list):
                return nested_items
        return []

    # ─────────────────────────────────────────────
    # 10. Envoyer un DM
    # ─────────────────────────────────────────────
    async def send_dm(self, ig_user_id: str, recipient_id: str, message: str) -> dict:
        """
        Envoie un message direct Instagram.
        Nécessite : instagram_manage_messages
        """
        return await self._post(
            f"{ig_user_id}/messages",
            json={
                "recipient": {"id": recipient_id},
                "message": {"text": message},
                "messaging_type": "RESPONSE",
            }
        )

    # ─────────────────────────────────────────────
    # 11. Insights (statistiques)
    # ─────────────────────────────────────────────
    async def get_account_insights(self, ig_user_id: str) -> dict:
        """
        Statistiques du compte : reach, impressions, followers.
        Nécessite : instagram_manage_insights
        """
        data = await self._get(
            f"{ig_user_id}/insights",
            metric="reach,impressions,follower_count,profile_views",
            period="day",
        )
        result = {}
        for item in data.get("data", []):
            values = item.get("values", [])
            result[item["name"]] = values[-1]["value"] if values else 0
        return result

    async def get_post_insights(self, media_id: str) -> dict:
        """
        Statistiques d'un post : reach, impressions, engagement.
        Nécessite : instagram_manage_insights
        """
        data = await self._get(
            f"{media_id}/insights",
            metric="reach,impressions,engagement,saved",
        )
        result = {}
        for item in data.get("data", []):
            result[item["name"]] = item.get("values", [{}])[0].get("value", 0)
        return result
