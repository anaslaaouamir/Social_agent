"""
TikTok API Service
Handles user info, video publishing, and account metrics via TikTok Content Posting API v2.
"""
from __future__ import annotations

import httpx
from loguru import logger
from typing import Optional

TIKTOK_API_BASE = "https://open.tiktokapis.com/v2"


class TikTokGraphService:
    """Wrapper around the TikTok API v2 for user-context operations."""

    def __init__(self, access_token: str):
        self.token = access_token
        self.client = httpx.AsyncClient(timeout=60)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    async def _get(self, path: str, params: dict | None = None) -> dict:
        resp = await self.client.get(
            f"{TIKTOK_API_BASE}/{path.lstrip('/')}",
            headers=self._headers(),
            params=params or {},
        )
        data = resp.json()
        if resp.status_code >= 400:
            raise ValueError(f"TikTok API error {resp.status_code}: {data}")
        err = data.get("error", {})
        if err.get("code") and err["code"] != "ok":
            raise ValueError(f"TikTok API error: {err.get('message', err['code'])}")
        return data

    async def _post(self, path: str, json: dict, params: dict | None = None) -> dict:
        resp = await self.client.post(
            f"{TIKTOK_API_BASE}/{path.lstrip('/')}",
            headers=self._headers(),
            json=json,
            params=params or {},
        )
        data = resp.json()
        if resp.status_code >= 400:
            raise ValueError(f"TikTok API error {resp.status_code}: {data}")
        err = data.get("error", {})
        if err.get("code") and err["code"] != "ok":
            raise ValueError(f"TikTok API error: {err.get('message', err['code'])}")
        return data

    async def close(self):
        await self.client.aclose()

    # ------------------------------------------------------------------ #
    # User Info                                                            #
    # ------------------------------------------------------------------ #
    async def get_user_info(self) -> dict:
        """
        Fetch basic info about the authenticated TikTok user.
        Requires scope: user.info.basic
        """
        data = await self._get(
            "user/info/",
            {"fields": "open_id,union_id,avatar_url,display_name,follower_count,following_count,likes_count,video_count"},
        )
        return data.get("data", {}).get("user", {})

    # ------------------------------------------------------------------ #
    # Video List                                                           #
    # ------------------------------------------------------------------ #
    async def get_user_videos(self, max_count: int = 20) -> list[dict]:
        """
        Fetch the authenticated user's videos.
        Requires scope: video.list
        NOTE: TikTok video/list/ requires 'fields' as a QUERY PARAM, not in the JSON body.
        """
        try:
            logger.info("TikTok get_user_videos: fetching videos...")
            data = await self._post(
                "video/list/",
                {"max_count": min(max_count, 20)},
                params={"fields": "id,title,cover_image_url,share_url,video_description,duration,height,width,like_count,comment_count,share_count,view_count,create_time"},
            )
            logger.info(f"TikTok get_user_videos response: {data}")
            return data.get("data", {}).get("videos", [])
        except Exception as e:
            logger.warning(f"TikTok get_user_videos failed: {e}")
            return []

    # ------------------------------------------------------------------ #
    # Video Publishing                                                     #
    # ------------------------------------------------------------------ #
    async def publish_video_from_url(
        self,
        video_url: str,
        title: str,
        privacy_level: str = "PUBLIC_TO_EVERYONE",
        disable_comment: bool = False,
        disable_duet: bool = False,
        disable_stitch: bool = False,
    ) -> dict:
        """
        Publish a video to TikTok from a public URL.
        Requires scope: video.publish
        privacy_level: PUBLIC_TO_EVERYONE | MUTUAL_FOLLOW_FRIENDS | FOLLOWER_OF_CREATOR | SELF_ONLY
        """
        data = await self._post(
            "post/publish/video/init/",
            {
                "post_info": {
                    "title": title[:150],
                    "privacy_level": privacy_level,
                    "disable_comment": disable_comment,
                    "disable_duet": disable_duet,
                    "disable_stitch": disable_stitch,
                },
                "source_info": {
                    "source": "PULL_FROM_URL",
                    "video_url": video_url,
                },
            },
        )
        return data.get("data", {})

    async def publish_video_direct(
        self,
        file_bytes: bytes,
        title: str,
        privacy_level: str = "PUBLIC_TO_EVERYONE",
        chunk_size: int = 1024 * 1024 * 10,  # 10 MB
    ) -> dict:
        """
        Publish a video to TikTok via direct file upload (chunked).
        Requires scope: video.publish
        """
        total_bytes = len(file_bytes)
        chunk_count = (total_bytes + chunk_size - 1) // chunk_size

        # Step 1: INIT
        init_data = await self._post(
            "post/publish/video/init/",
            {
                "post_info": {
                    "title": title[:150],
                    "privacy_level": privacy_level,
                    "disable_comment": False,
                    "disable_duet": False,
                    "disable_stitch": False,
                },
                "source_info": {
                    "source": "PUSH_TO_URL",
                    "video_size": total_bytes,
                },
            },
        )
        publish_id = init_data.get("data", {}).get("publish_id")
        upload_url = init_data.get("data", {}).get("upload_url")
        if not publish_id or not upload_url:
            raise ValueError(f"TikTok INIT failed (no upload_url): {init_data}")

        # Step 2: Upload video bytes to upload_url
        upload_resp = await self.client.put(
            upload_url,
            content=file_bytes,
            headers={
                "Content-Type": "application/octet-stream",
                "Content-Length": str(total_bytes),
            },
        )
        if upload_resp.status_code not in {200, 201, 204, 202}:
            raise ValueError(f"TikTok upload failed ({upload_resp.status_code}): {upload_resp.text[:500]}")
        logger.info(f"TikTok: video uploaded successfully")

        return {"publish_id": publish_id}

    # ------------------------------------------------------------------ #
    # Video Comments                                                      #
    # ------------------------------------------------------------------ #
    async def get_video_comments(self, video_id: str, max_count: int = 20, cursor: int = 0) -> list[dict]:
        """
        Fetch comments for a specific video.
        Requires scope: video.comment
        """
        try:
            data = await self._post(
                "video/comment/list/",
                {
                    "fields": "id,text,like_count,create_time,author,reply_comment_total",
                    "video_id": video_id,
                    "max_count": min(max_count, 20),
                    "cursor": cursor,
                },
            )
            comments = data.get("data", {}).get("comments", [])
            return comments
        except Exception as e:
            logger.warning(f"TikTok get_video_comments failed: {e}")
            return []

    async def get_publish_status(self, publish_id: str) -> dict:
        """Check the status of a video publish operation."""
        data = await self._post(
            "post/publish/status/fetch/",
            {"publish_id": publish_id},
        )
        return data.get("data", {})

    # ------------------------------------------------------------------ #
    # Account Metrics                                                      #
    # ------------------------------------------------------------------ #
    async def get_account_metrics(self) -> dict:
        """Returns follower count and basic engagement metrics."""
        try:
            user = await self.get_user_info()
            return {
                "followers_count": user.get("follower_count", 0),
                "following_count": user.get("following_count", 0),
                "likes_count": user.get("likes_count", 0),
                "video_count": user.get("video_count", 0),
            }
        except Exception as e:
            logger.warning(f"TikTok get_account_metrics failed: {e}")
            return {}