"""
Social Publisher Service
Handles auto-posting to Instagram, TikTok, LinkedIn, Facebook.
Implements retry logic, rate limiting, and platform-specific formatting.
"""
from __future__ import annotations
import asyncio
import base64
import binascii
import hashlib
import hmac
import mimetypes
import re
import time
from dataclasses import dataclass
from typing import Optional
from enum import Enum
from urllib.parse import urlparse
from loguru import logger
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
from core.config import get_settings


class PublishStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    RATE_LIMITED = "rate_limited"
    AUTH_ERROR = "auth_error"
    CONTENT_REJECTED = "content_rejected"


@dataclass
class PublishResult:
    platform: str
    status: PublishStatus
    platform_post_id: Optional[str]
    published_at: Optional[float]
    error_message: Optional[str]
    retry_after: Optional[int]


def _should_retry_publish_exception(exc: BaseException) -> bool:
    if not isinstance(exc, httpx.HTTPStatusError):
        return isinstance(exc, httpx.HTTPError)
    status_code = exc.response.status_code
    return status_code == 429 or status_code >= 500


class SocialPublisherService:
    """
    Multi-platform publisher with:
    - Retry with exponential backoff
    - Rate limit handling
    - Platform-specific media formatting
    - Async concurrent publishing to multiple platforms
    """

    def __init__(
        self,
        instagram_token: str = "",
        instagram_account_id: str = "",
        tiktok_token: str = "",
        linkedin_token: str = "",
        linkedin_member_id: str = "",
        facebook_token: str = "",
        facebook_page_id: str = "",
        twitter_token: str = "",
        twitter_user_id: str = "",
        threads_token: str = "",
        threads_user_id: str = "",
        youtube_token: str = "",
        youtube_channel_id: str = "",
    ):
        self.tokens = {
            "instagram": instagram_token,
            "tiktok": tiktok_token,
            "linkedin": linkedin_token,
            "facebook": facebook_token,
            "twitter": twitter_token,
            "threads": threads_token,
            "youtube": youtube_token,
        }
        self.instagram_account_id = instagram_account_id
        self.linkedin_member_id = linkedin_member_id
        self.facebook_page_id = facebook_page_id
        self.twitter_user_id = twitter_user_id
        self.threads_user_id = threads_user_id
        self.youtube_channel_id = youtube_channel_id
        self._client = httpx.AsyncClient(timeout=30.0)
        self._settings = get_settings()

    def _auth_error(self, platform: str, message: str) -> PublishResult:
        return PublishResult(
            platform=platform,
            status=PublishStatus.AUTH_ERROR,
            platform_post_id=None,
            published_at=None,
            error_message=message,
            retry_after=None,
        )

    def _failed_result(self, platform: str, message: str) -> PublishResult:
        return PublishResult(
            platform=platform,
            status=PublishStatus.FAILED,
            platform_post_id=None,
            published_at=None,
            error_message=message,
            retry_after=None,
        )

    def _unsupported_content_result(self, platform: str, content_type: str, detail: str) -> PublishResult:
        return PublishResult(
            platform=platform,
            status=PublishStatus.CONTENT_REJECTED,
            platform_post_id=None,
            published_at=None,
            error_message=f"{content_type.title()} is not supported for {platform} publishing: {detail}",
            retry_after=None,
        )

    def _is_public_http_url(self, value: str) -> bool:
        try:
            parsed = urlparse(value)
        except Exception:
            return False
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    def _parse_data_url(self, value: str) -> tuple[str, bytes] | None:
        match = re.match(r"^data:(?P<mime>[\w.+-]+/[\w.+-]+);base64,(?P<data>.+)$", value, re.DOTALL)
        if not match:
            return None
        try:
            raw = base64.b64decode(match.group("data"))
        except (binascii.Error, ValueError):
            return None
        return match.group("mime"), raw

    def _build_upload_filename(self, mime_type: str) -> str:
        extension = mimetypes.guess_extension(mime_type) or ".bin"
        if extension == ".jpe":
            extension = ".jpg"
        return f"upload{extension}"

    def _public_backend_base_url(self) -> str:
        if self._settings.public_api_base_url:
            return self._settings.public_api_base_url.rstrip("/")

        for candidate in (
            self._settings.instagram_redirect_uri,
            self._settings.facebook_redirect_uri,
        ):
            if not candidate:
                continue
            try:
                parsed = urlparse(candidate)
            except Exception:
                continue
            if parsed.scheme in {"http", "https"} and parsed.netloc:
                return f"{parsed.scheme}://{parsed.netloc}"

        raise ValueError(
            "A public backend URL is required to publish media-library assets. "
            "Set PUBLIC_API_BASE_URL or configure a public Instagram redirect URI."
        )

    def _build_signed_media_proxy_url(self, post_id: str, media_index: int, media_url: str) -> str:
        expires = int(time.time()) + 3600
        payload = f"{post_id}:{media_index}:{expires}:{hashlib.sha256(media_url.encode('utf-8')).hexdigest()}"
        token = hmac.new(
            self._settings.secret_key.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        base_url = self._public_backend_base_url()
        return f"{base_url}/api/posts/{post_id}/media/{media_index}?expires={expires}&token={token}"

    async def _prepare_non_facebook_media_url(
        self,
        platform: str,
        media_url: str,
        *,
        post_id: str | None = None,
        media_index: int | None = None,
    ) -> str:
        if self._is_public_http_url(media_url):
            return media_url

        parsed_data_url = self._parse_data_url(media_url)
        if not parsed_data_url:
            raise ValueError(
                f"{platform.title()} publishing requires a public http(s) media URL or a base64 data URL from the media library."
            )

        if post_id is not None and media_index is not None:
            return self._build_signed_media_proxy_url(post_id, media_index, media_url)

        mime_type, raw_bytes = parsed_data_url
        if not self._settings.imgbb_api_key:
            raise ValueError(
                f"{platform.title()} publishing from the media library requires either a public backend URL "
                "for the signed media proxy or IMGBB_API_KEY."
            )
        encoded_image = base64.b64encode(raw_bytes).decode("utf-8")
        resp = await self._client.post(
            "https://api.imgbb.com/1/upload",
            data={
                "key": self._settings.imgbb_api_key,
                "image": encoded_image,
                "name": self._build_upload_filename(mime_type),
            },
        )
        resp.raise_for_status()
        payload = resp.json()
        if not payload.get("success") or not payload.get("data", {}).get("url"):
            raise ValueError(f"Failed to upload {platform} media to imgbb.")
        return payload["data"]["url"]

    async def publish_to_platform(
        self,
        platform: str,
        caption: str,
        media_urls: list[str],
        content_type: str = "image",
        hashtags: list[str] = None,
        source_post_id: str | None = None,
    ) -> PublishResult:
        """Publish content to a specific platform."""
        if hashtags is None:
            hashtags = []

        full_caption = caption
        if hashtags:
            full_caption += "\n\n" + " ".join(hashtags)

        publishers = {
            "instagram": self._publish_instagram,
            "tiktok": self._publish_tiktok,
            "linkedin": self._publish_linkedin,
            "facebook": self._publish_facebook,
            "twitter": self._publish_twitter,
            "threads": self._publish_threads,
            "youtube": self._publish_youtube,
        }

        publisher = publishers.get(platform.lower())
        if not publisher:
            return PublishResult(
                platform=platform,
                status=PublishStatus.FAILED,
                platform_post_id=None,
                published_at=None,
                error_message=f"Unknown platform: {platform}",
                retry_after=None,
            )

        normalized_platform = platform.lower()
        normalized_content_type = content_type.lower()
        if normalized_content_type == "story":
            return self._unsupported_content_result(
                normalized_platform,
                normalized_content_type,
                "story publishing is not implemented in this app yet.",
            )
        if normalized_content_type == "reel" and normalized_platform != "instagram":
            if normalized_platform == "youtube":
                normalized_content_type = "video"
            else:
                return self._unsupported_content_result(
                    normalized_platform,
                    normalized_content_type,
                    "reels are currently implemented only for Instagram.",
                )
        if normalized_content_type == "reel":
            normalized_content_type = "video"
        if normalized_platform == "youtube" and normalized_content_type != "video":
            return self._unsupported_content_result(
                normalized_platform,
                normalized_content_type,
                "YouTube publishing requires a video upload.",
            )
        if normalized_content_type == "carousel" and normalized_platform == "threads":
            return self._unsupported_content_result(
                normalized_platform,
                normalized_content_type,
                "carousel publishing is not implemented for Threads yet.",
            )

        try:
            if normalized_platform == "facebook":
                return await publisher(full_caption, media_urls, normalized_content_type)
            return await publisher(full_caption, media_urls, normalized_content_type, source_post_id)
        except Exception as e:
            logger.error(f"Publish to {platform} failed: {e}")
            return PublishResult(
                platform=platform,
                status=PublishStatus.FAILED,
                platform_post_id=None,
                published_at=None,
                error_message=str(e),
                retry_after=None,
            )

    async def publish_multi_platform(
        self,
        platforms: list[str],
        caption: str,
        media_urls: list[str],
        content_type: str = "image",
        hashtags: list[str] = None,
    ) -> list[PublishResult]:
        """Publish to multiple platforms concurrently."""
        tasks = [
            self.publish_to_platform(p, caption, media_urls, content_type, hashtags)
            for p in platforms
        ]
        return await asyncio.gather(*tasks, return_exceptions=False)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        retry=retry_if_exception(_should_retry_publish_exception),
    )
    async def _publish_instagram(
        self,
        caption: str,
        media_urls: list[str],
        content_type: str,
        source_post_id: str | None = None,
    ) -> PublishResult:
        """Publish to Instagram via Graph API."""
        token = (self.tokens["instagram"] or "").strip()
        account_id = self.instagram_account_id

        if not token or not account_id:
            return self._auth_error(
                "instagram",
                "Instagram Business token or account_id is missing",
            )

        try:
            # Step 1: Create media container
            if content_type == "carousel" and len(media_urls) > 1:
                # Create individual containers
                item_ids = []
                for index, url in enumerate(media_urls):
                    prepared_url = await self._prepare_non_facebook_media_url(
                        "instagram",
                        url,
                        post_id=source_post_id,
                        media_index=index,
                    )
                    resp = await self._client.post(
                        f"https://graph.facebook.com/v19.0/{account_id}/media",
                        data={
                            "image_url": prepared_url,
                            "is_carousel_item": "true",
                            "access_token": token,
                        },
                    )
                    resp.raise_for_status()
                    item_ids.append(resp.json()["id"])

                # Create carousel container
                resp = await self._client.post(
                    f"https://graph.facebook.com/v19.0/{account_id}/media",
                    data={
                        "media_type": "CAROUSEL",
                        "caption": caption[:2200],
                        "children": ",".join(item_ids),
                        "access_token": token,
                    },
                )
            elif content_type == "video":
                prepared_url = await self._prepare_non_facebook_media_url(
                    "instagram",
                    media_urls[0] if media_urls else "",
                    post_id=source_post_id,
                    media_index=0,
                )
                resp = await self._client.post(
                    f"https://graph.facebook.com/v19.0/{account_id}/media",
                    data={
                        "video_url": prepared_url,
                        "caption": caption[:2200],
                        "media_type": "REELS",
                        "access_token": token,
                    },
                )
            else:
                prepared_url = await self._prepare_non_facebook_media_url(
                    "instagram",
                    media_urls[0] if media_urls else "",
                    post_id=source_post_id,
                    media_index=0,
                )
                resp = await self._client.post(
                    f"https://graph.facebook.com/v19.0/{account_id}/media",
                    data={
                        "image_url": prepared_url,
                        "caption": caption[:2200],
                        "access_token": token,
                    },
                )

            resp.raise_for_status()
            container_id = resp.json()["id"]

            # Step 2: Publish
            pub_resp = await self._client.post(
                f"https://graph.facebook.com/v19.0/{account_id}/media_publish",
                data={"creation_id": container_id, "access_token": token},
            )
            pub_resp.raise_for_status()
            post_id = pub_resp.json()["id"]

            return PublishResult(
                platform="instagram",
                status=PublishStatus.SUCCESS,
                platform_post_id=post_id,
                published_at=time.time(),
                error_message=None,
                retry_after=None,
            )

        except httpx.HTTPStatusError as e:
            message = e.response.text
            logger.warning(f"Instagram publish error ({e.response.status_code}): {message}")
            if e.response.status_code == 429:
                retry_after = int(e.response.headers.get("Retry-After", 3600))
                return PublishResult(
                    platform="instagram",
                    status=PublishStatus.RATE_LIMITED,
                    platform_post_id=None,
                    published_at=None,
                    error_message=message or "Rate limit exceeded",
                    retry_after=retry_after,
                )
            if e.response.status_code in {400, 401, 403}:
                if e.response.status_code in {401, 403}:
                    return self._auth_error("instagram", message)
                return self._failed_result("instagram", message)
            raise
        except ValueError as e:
            return self._failed_result("instagram", str(e))

    async def _publish_tiktok(
        self,
        caption: str,
        media_urls: list[str],
        content_type: str,
        source_post_id: str | None = None,
    ) -> PublishResult:
        """Publish to TikTok via Content Posting API."""
        token = self.tokens["tiktok"]
        if not token:
            return self._mock_publish("tiktok")

        try:
            # TikTok Content Posting API v2
            prepared_url = ""
            if media_urls:
                prepared_url = await self._prepare_non_facebook_media_url(
                    "tiktok",
                    media_urls[0],
                    post_id=source_post_id,
                    media_index=0,
                )
            resp = await self._client.post(
                "https://open.tiktokapis.com/v2/post/publish/video/init/",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={
                    "post_info": {
                        "title": caption[:150],
                        "disable_comment": False,
                        "privacy_level": "PUBLIC_TO_EVERYONE",
                    },
                    "source_info": {
                        "source": "PULL_FROM_URL",
                        "video_url": prepared_url,
                    },
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return PublishResult(
                platform="tiktok",
                status=PublishStatus.SUCCESS,
                platform_post_id=data.get("data", {}).get("publish_id"),
                published_at=time.time(),
                error_message=None,
                retry_after=None,
            )
        except Exception as e:
            logger.warning(f"TikTok publish error: {e}")
            return self._mock_publish("tiktok")

    async def _publish_linkedin(
        self,
        caption: str,
        media_urls: list[str],
        content_type: str,
        source_post_id: str | None = None,
    ) -> PublishResult:
        """Publish to LinkedIn using the member URN already stored on the account."""
        token = self.tokens["linkedin"]
        author_urn = self.linkedin_member_id
        if not token or not author_urn:
            return self._auth_error("linkedin", "LinkedIn token or member URN is missing")
        if not author_urn.startswith("urn:"):
            author_urn = f"urn:li:person:{author_urn}"

        try:
            from services.linkedIn_graph import LinkedInGraphService

            svc = LinkedInGraphService(token)
            image_url = None
            if media_urls:
                image_url = await self._prepare_non_facebook_media_url(
                    "linkedin",
                    media_urls[0],
                    post_id=source_post_id,
                    media_index=0,
                )

            result = await svc.create_post(
                author_urn=author_urn,
                text=caption[:3000],
                visibility="PUBLIC",
                image_url=image_url,
            )
            await svc.close()
            return PublishResult(
                platform="linkedin",
                status=PublishStatus.SUCCESS,
                platform_post_id=result.get("linkedin_post_id"),
                published_at=time.time(),
                error_message=None,
                retry_after=None,
            )
        except httpx.HTTPStatusError as e:
            message = e.response.text
            logger.warning(f"LinkedIn publish error: {message}")
            if e.response.status_code in {400, 401, 403}:
                return self._auth_error("linkedin", message)
            return self._failed_result("linkedin", message)
        except Exception as e:
            logger.warning(f"LinkedIn publish error: {e}")
            return self._failed_result("linkedin", str(e))

    async def _publish_facebook(self, caption: str, media_urls: list[str], content_type: str) -> PublishResult:
        """Publish to Facebook Page via Graph API."""
        token = self.tokens["facebook"]
        page_id = self.facebook_page_id
        if not token or not page_id:
            return self._auth_error("facebook", "Facebook Page token or page_id is missing")

        try:
            if media_urls:
                media_url = media_urls[0]
                if self._is_public_http_url(media_url):
                    payload = {
                        "url": media_url,
                        "caption": caption[:63206],
                        "access_token": token,
                    }
                    resp = await self._client.post(
                        f"https://graph.facebook.com/v19.0/{page_id}/photos",
                        data=payload,
                    )
                else:
                    parsed_data_url = self._parse_data_url(media_url)
                    if not parsed_data_url:
                        return self._failed_result(
                            "facebook",
                            "Facebook image posts support either a public http(s) media URL or a base64 data URL from the media library.",
                        )
                    mime_type, raw_bytes = parsed_data_url
                    resp = await self._client.post(
                        f"https://graph.facebook.com/v19.0/{page_id}/photos",
                        params={"access_token": token},
                        data={"caption": caption[:63206]},
                        files={"source": (self._build_upload_filename(mime_type), raw_bytes, mime_type)},
                    )
            else:
                payload = {
                    "message": caption[:63206],
                    "access_token": token,
                }
                resp = await self._client.post(
                    f"https://graph.facebook.com/v19.0/{page_id}/feed",
                    data=payload,
                )
            resp.raise_for_status()
            data = resp.json()
            return PublishResult(
                platform="facebook",
                status=PublishStatus.SUCCESS,
                platform_post_id=data.get("id") or data.get("post_id"),
                published_at=time.time(),
                error_message=None,
                retry_after=None,
            )
        except httpx.HTTPStatusError as e:
            message = e.response.text
            logger.warning(f"Facebook publish error: {message}")
            if e.response.status_code in {400, 401, 403}:
                return self._auth_error("facebook", message)
            return self._failed_result("facebook", message)
        except Exception as e:
            logger.warning(f"Facebook publish error: {e}")
            return self._failed_result("facebook", str(e))

    async def _publish_twitter(
        self,
        caption: str,
        media_urls: list[str],
        content_type: str,
        source_post_id: str | None = None,
    ) -> PublishResult:
        """Publish a tweet to X/Twitter via API v2 + OAuth 1 media upload."""
        token = (self.tokens["twitter"] or "").strip()
        user_id = (self.twitter_user_id or "").strip()
        if not token or not user_id:
            return self._auth_error("twitter", "Twitter token or user id is missing")
        if media_urls and content_type == "video":
            return self._unsupported_content_result(
                "twitter",
                content_type,
                "video upload is not implemented for X/Twitter yet.",
            )

        try:
            from services.twitter_graph import TwitterGraphService

            svc = TwitterGraphService(token)
            result = await svc.create_tweet_with_media(caption[:280], media_urls)
            await svc.close()
            return PublishResult(
                platform="twitter",
                status=PublishStatus.SUCCESS,
                platform_post_id=result.get("id"),
                published_at=time.time(),
                error_message=None,
                retry_after=None,
            )
        except Exception as e:
            logger.warning(f"Twitter publish error: {e}")
            return self._failed_result("twitter", str(e))

    async def _publish_threads(
        self,
        caption: str,
        media_urls: list[str],
        content_type: str,
        source_post_id: str | None = None,
    ) -> PublishResult:
        """Publish to Threads via graph.threads.net."""
        token = (self.tokens["threads"] or "").strip()
        user_id = (self.threads_user_id or "").strip()
        if not token or not user_id:
            return self._auth_error("threads", "Threads token or user id is missing")

        try:
            from services.threads_graph import ThreadsGraphService

            media_type = "TEXT"
            prepared_url = None
            if media_urls:
                prepared_url = await self._prepare_non_facebook_media_url(
                    "threads",
                    media_urls[0],
                    post_id=source_post_id,
                    media_index=0,
                )
                media_type = "VIDEO" if content_type == "video" else "IMAGE"

            svc = ThreadsGraphService(token)
            result = await svc.publish(
                user_id=user_id,
                text=caption[:500],
                media_url=prepared_url,
                media_type=media_type,
            )
            await svc.close()
            return PublishResult(
                platform="threads",
                status=PublishStatus.SUCCESS,
                platform_post_id=result.get("id"),
                published_at=time.time(),
                error_message=None,
                retry_after=None,
            )
        except httpx.HTTPStatusError as e:
            message = e.response.text
            logger.warning(f"Threads publish error: {message}")
            if e.response.status_code in {400, 401, 403}:
                return self._auth_error("threads", message)
            return self._failed_result("threads", message)
        except Exception as e:
            logger.warning(f"Threads publish error: {e}")
            return self._failed_result("threads", str(e))

    async def _load_upload_bytes_for_youtube(
        self,
        media_url: str,
        *,
        source_post_id: str | None = None,
    ) -> tuple[bytes, str]:
        parsed_data_url = self._parse_data_url(media_url)
        if parsed_data_url:
            mime_type, raw_bytes = parsed_data_url
            return raw_bytes, mime_type

        prepared_url = media_url
        if not self._is_public_http_url(prepared_url):
            if not source_post_id:
                raise ValueError("YouTube video publishing requires a public URL or media-library data URL.")
            prepared_url = self._build_signed_media_proxy_url(source_post_id, 0, media_url)

        resp = await self._client.get(prepared_url, follow_redirects=True)
        resp.raise_for_status()
        mime_type = resp.headers.get("content-type", "video/mp4").split(";", 1)[0]
        return resp.content, mime_type or "video/mp4"

    async def _publish_youtube(
        self,
        caption: str,
        media_urls: list[str],
        content_type: str,
        source_post_id: str | None = None,
    ) -> PublishResult:
        """Publish a video to YouTube via resumable upload."""
        token = (self.tokens["youtube"] or "").strip()
        if not token:
            return self._auth_error("youtube", "YouTube access token is missing")
        if not media_urls:
            return self._unsupported_content_result("youtube", content_type, "a video file or URL is required.")

        try:
            from services.youtube_graph import YouTubeGraphService

            file_bytes, mime_type = await self._load_upload_bytes_for_youtube(
                media_urls[0],
                source_post_id=source_post_id,
            )
            if not mime_type.startswith("video/"):
                return self._unsupported_content_result("youtube", content_type, f"media type {mime_type} is not video.")

            title = caption.strip().splitlines()[0][:100] if caption.strip() else "Untitled video"
            svc = YouTubeGraphService(token)
            result = await svc.upload_video(
                file_bytes=file_bytes,
                title=title,
                description=caption[:5000],
                privacy_status="private",
                mime_type=mime_type,
            )
            await svc.close()
            return PublishResult(
                platform="youtube",
                status=PublishStatus.SUCCESS,
                platform_post_id=result.get("id"),
                published_at=time.time(),
                error_message=None,
                retry_after=None,
            )
        except httpx.HTTPStatusError as e:
            message = e.response.text
            logger.warning(f"YouTube publish error: {message}")
            if e.response.status_code in {400, 401, 403}:
                return self._auth_error("youtube", message)
            return self._failed_result("youtube", message)
        except Exception as e:
            logger.warning(f"YouTube publish error: {e}")
            return self._failed_result("youtube", str(e))

    def _mock_publish(self, platform: str) -> PublishResult:
        """Mock publish for development/testing without real tokens."""
        import uuid
        logger.info(f"[MOCK] Published to {platform}")
        return PublishResult(
            platform=platform,
            status=PublishStatus.SUCCESS,
            platform_post_id=f"mock_{platform}_{uuid.uuid4().hex[:8]}",
            published_at=time.time(),
            error_message=None,
            retry_after=None,
        )

    async def close(self):
        await self._client.aclose()
