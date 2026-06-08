"""Small Threads Graph API client for profile, reading and publishing."""
from __future__ import annotations

import httpx


THREADS_BASE = "https://graph.threads.net/v1.0"


class ThreadsGraphService:
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.client = httpx.AsyncClient(timeout=30)

    async def _get(self, path: str, params: dict | None = None) -> dict:
        payload = {"access_token": self.access_token, **(params or {})}
        resp = await self.client.get(f"{THREADS_BASE}{path}", params=payload)
        data = resp.json()
        if resp.status_code >= 400 or data.get("error"):
            message = (data.get("error") or {}).get("message") or resp.text
            raise ValueError(f"Threads API error: {message}")
        return data

    async def _post(self, path: str, data: dict | None = None) -> dict:
        payload = {"access_token": self.access_token, **(data or {})}
        resp = await self.client.post(f"{THREADS_BASE}{path}", data=payload)
        body = resp.json()
        if resp.status_code >= 400 or body.get("error"):
            message = (body.get("error") or {}).get("message") or resp.text
            raise ValueError(f"Threads API error: {message}")
        return body

    async def get_profile(self) -> dict:
        return await self._get(
            "/me",
            {
                "fields": "id,username,threads_profile_picture_url,threads_biography",
            },
        )

    async def get_threads(self, user_id: str = "me", limit: int = 20) -> list[dict]:
        data = await self._get(
            f"/{user_id}/threads",
            {
                "fields": "id,text,media_type,media_url,permalink,timestamp,like_count,reply_count,repost_count,quote_count",
                "limit": str(limit),
            },
        )
        return data.get("data", [])

    async def publish(
        self,
        user_id: str,
        text: str,
        media_url: str | None = None,
        media_type: str = "TEXT",
    ) -> dict:
        container_payload = {
            "media_type": media_type,
            "text": text,
        }
        if media_type == "IMAGE" and media_url:
            container_payload["image_url"] = media_url
        if media_type == "VIDEO" and media_url:
            container_payload["video_url"] = media_url

        container = await self._post(f"/{user_id}/threads", container_payload)
        creation_id = container.get("id")
        if not creation_id:
            raise ValueError("Threads media container did not return an id")

        # For videos, we must wait for Meta to finish processing before publishing
        if media_type == "VIDEO":
            import asyncio
            for _ in range(60):
                await asyncio.sleep(5)
                status_resp = await self._get(f"/{creation_id}", {"fields": "status,error_message"})
                status = status_resp.get("status")
                if status == "FINISHED":
                    break
                if status == "ERROR":
                    error_msg = status_resp.get("error_message", "Unknown video processing error")
                    raise ValueError(f"Threads video processing failed: {error_msg}")

        return await self._post(f"/{user_id}/threads_publish", {"creation_id": creation_id})

    async def close(self) -> None:
        await self.client.aclose()



    async def get_media_insights(self, media_id: str) -> dict:
        """Fetch insights for a specific Threads post."""
        data = await self._get(
            f"/{media_id}/insights",
            {"metric": "views,likes,replies,reposts,quotes"}
        )
        insights = {}
        for item in data.get("data", []):
            vals = item.get("values", [])
            if vals and len(vals) > 0:
                insights[item["name"]] = vals[0].get("value", 0)
        return insights

    async def get_replies(self, media_id: str) -> list[dict]:
        """Fetch replies (comments) for a specific Threads post."""
        data = await self._get(
            f"/{media_id}/replies",
            {"fields": "id,text,timestamp,username"}
        )
        top_replies = data.get("data", [])
        
        if not top_replies:
            return []
            
        import asyncio
        async def fetch_nested(reply):
            try:
                nested_data = await self._get(
                    f"/{reply['id']}/replies",
                    {"fields": "id,text,timestamp,username"}
                )
                reply["replies"] = nested_data
            except Exception:
                pass

        await asyncio.gather(*(fetch_nested(r) for r in top_replies))
        return top_replies

    async def reply_to_comment(self, user_id: str, reply_to_id: str, text: str) -> dict:
        """Reply to a specific Threads comment or post."""
        container = await self._post(f"/{user_id}/threads", {
            "media_type": "TEXT",
            "text": text,
            "reply_to_id": reply_to_id
        })
        creation_id = container.get("id")
        if not creation_id:
            raise ValueError("Threads media container did not return an id")
        return await self._post(f"/{user_id}/threads_publish", {"creation_id": creation_id})