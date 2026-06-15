"""YouTube Data API and Analytics API client."""
from __future__ import annotations

import httpx


YOUTUBE_DATA_BASE = "https://www.googleapis.com/youtube/v3"
YOUTUBE_ANALYTICS_BASE = "https://youtubeanalytics.googleapis.com/v2"
YOUTUBE_UPLOAD_BASE = "https://www.googleapis.com/upload/youtube/v3"


class YouTubeGraphService:
    """Wrapper for authenticated YouTube channel operations."""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.client = httpx.AsyncClient(timeout=120)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}

    async def _get(self, base_url: str, path: str, params: dict | None = None) -> dict:
        resp = await self.client.get(
            f"{base_url}/{path.lstrip('/')}",
            headers=self._headers(),
            params=params or {},
        )
        data = resp.json()
        if resp.status_code >= 400 or data.get("error"):
            message = (data.get("error") or {}).get("message") or resp.text
            raise ValueError(f"YouTube API error {resp.status_code}: {message}")
        return data

    async def _post(self, base_url: str, path: str, json: dict | None = None, params: dict | None = None) -> dict:
        resp = await self.client.post(
            f"{base_url}/{path.lstrip('/')}",
            headers={**self._headers(), "Content-Type": "application/json"},
            params=params or {},
            json=json or {},
        )
        data = resp.json() if resp.content else {}
        if resp.status_code >= 400 or data.get("error"):
            message = (data.get("error") or {}).get("message") or resp.text
            raise ValueError(f"YouTube API error {resp.status_code}: {message}")
        return data

    async def close(self) -> None:
        await self.client.aclose()

    async def get_my_channel(self) -> dict:
        """Fetch authenticated user's channel info. Requires youtube.readonly."""
        data = await self._get(
            YOUTUBE_DATA_BASE,
            "channels",
            {
                "part": "id,snippet,statistics,contentDetails",
                "mine": "true",
                "maxResults": 1,
            },
        )
        items = data.get("items", [])
        if not items:
            raise ValueError("No YouTube channel found for authenticated user")
        return items[0]

    async def get_channel_videos(self, channel_id: str | None = None, max_results: int = 20) -> list[dict]:
        """Fetch recent videos through the channel uploads playlist."""
        channel = await self.get_my_channel()
        uploads_playlist = (
            channel.get("contentDetails", {})
            .get("relatedPlaylists", {})
            .get("uploads")
        )
        if not uploads_playlist:
            return []

        playlist_data = await self._get(
            YOUTUBE_DATA_BASE,
            "playlistItems",
            {
                "part": "snippet,contentDetails",
                "playlistId": uploads_playlist,
                "maxResults": min(max_results, 50),
            },
        )
        video_ids = [
            item.get("contentDetails", {}).get("videoId")
            for item in playlist_data.get("items", [])
            if item.get("contentDetails", {}).get("videoId")
        ]
        if not video_ids:
            return []

        video_data = await self._get(
            YOUTUBE_DATA_BASE,
            "videos",
            {
                "part": "id,snippet,statistics,contentDetails,status",
                "id": ",".join(video_ids),
                "maxResults": min(max_results, 50),
            },
        )
        return video_data.get("items", [])

    async def get_video_comments(self, video_id: str, max_results: int = 50) -> list[dict]:
        """Fetch top-level comments. Requires youtube.force-ssl."""
        data = await self._get(
            YOUTUBE_DATA_BASE,
            "commentThreads",
            {
                "part": "snippet,replies",
                "videoId": video_id,
                "maxResults": min(max_results, 100),
                "textFormat": "plainText",
                "order": "time",
            },
        )
        return data.get("items", [])

    async def add_comment(self, video_id: str, text: str) -> dict:
        """Add a top-level video comment. Requires youtube.force-ssl."""
        return await self._post(
            YOUTUBE_DATA_BASE,
            "commentThreads",
            params={"part": "snippet"},
            json={
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {"textOriginal": text},
                    },
                },
            },
        )

    async def reply_to_comment(self, parent_id: str, text: str) -> dict:
        """Reply to a comment. Requires youtube.force-ssl."""
        return await self._post(
            YOUTUBE_DATA_BASE,
            "comments",
            params={"part": "snippet"},
            json={
                "snippet": {
                    "parentId": parent_id,
                    "textOriginal": text,
                },
            },
        )

    async def get_channel_analytics(
        self,
        channel_id: str,
        start_date: str,
        end_date: str,
        metrics: str = "views,likes,comments,shares,estimatedMinutesWatched,subscribersGained",
        dimensions: str = "day",
    ) -> dict:
        """Fetch YouTube Analytics report. Requires yt-analytics.readonly."""
        return await self._get(
            YOUTUBE_ANALYTICS_BASE,
            "reports",
            {
                "ids": f"channel=={channel_id}",
                "startDate": start_date,
                "endDate": end_date,
                "metrics": metrics,
                "dimensions": dimensions,
                "sort": dimensions,
            },
        )

    async def upload_video(
        self,
        file_bytes: bytes,
        title: str,
        description: str = "",
        tags: list[str] | None = None,
        category_id: str = "22",
        privacy_status: str = "public",
        mime_type: str = "video/mp4",
    ) -> dict:
        """Upload a video using YouTube resumable upload. Requires youtube.upload."""
        metadata = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags or [],
                "categoryId": category_id,
            },
            "status": {"privacyStatus": privacy_status},
        }
        init_resp = await self.client.post(
            f"{YOUTUBE_UPLOAD_BASE}/videos",
            headers={
                **self._headers(),
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": mime_type,
                "X-Upload-Content-Length": str(len(file_bytes)),
            },
            params={"uploadType": "resumable", "part": "snippet,status"},
            json=metadata,
        )
        if init_resp.status_code >= 400:
            raise ValueError(f"YouTube upload init failed {init_resp.status_code}: {init_resp.text}")

        upload_url = init_resp.headers.get("Location")
        if not upload_url:
            raise ValueError("YouTube upload init did not return a resumable upload URL")

        upload_resp = await self.client.put(
            upload_url,
            headers={
                "Content-Type": mime_type,
                "Content-Length": str(len(file_bytes)),
            },
            content=file_bytes,
        )
        data = upload_resp.json() if upload_resp.content else {}
        if upload_resp.status_code >= 400 or data.get("error"):
            message = (data.get("error") or {}).get("message") or upload_resp.text
            raise ValueError(f"YouTube upload failed {upload_resp.status_code}: {message}")
        return data
