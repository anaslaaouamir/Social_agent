"""
Twitter/X API service.
Supports OAuth 2.0 user-context profile lookup, tweet publishing, and OAuth 1.0a media upload.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import mimetypes
import re
import secrets
import time
from urllib.parse import quote, urlsplit

import httpx

from core.config import get_settings


X_API_BASE = "https://api.twitter.com/2"
X_UPLOAD_API_BASE = "https://upload.twitter.com/1.1"
_DATA_URL_RE = re.compile(r"^data:(?P<mime>[\w.+-]+/[\w.+-]+);base64,(?P<data>.+)$", re.DOTALL)


def _format_twitter_error(kind: str, status_code: int, data: object) -> str:
    if isinstance(data, dict):
        title = str(data.get("title") or "").strip()
        detail = str(data.get("detail") or "").strip()
        error_type = str(data.get("type") or "").strip()
        errors = data.get("errors")

        if title == "CreditsDepleted" or error_type.endswith("/problems/credits"):
            detail_text = detail or "The enrolled X developer account has no credits remaining."
            return f"Twitter credits depleted: {detail_text}"

        if isinstance(errors, list):
            for item in errors:
                if not isinstance(item, dict):
                    continue
                code = item.get("code")
                message = str(item.get("message") or "").strip()
                if code == 32:
                    return (
                        "Twitter OAuth1 media token invalid: "
                        f"{message or 'Could not authenticate the media upload request.'}"
                    )

        if detail:
            return f"Twitter {kind} error {status_code}: {detail}"

    return f"Twitter {kind} error {status_code}: {data}"


class TwitterGraphService:
    """Minimal wrapper around the X API for user-context operations."""

    def __init__(self, access_token: str):
        self.token = access_token
        self.client = httpx.AsyncClient(timeout=30)
        self.settings = get_settings()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _oauth1_credentials(self) -> tuple[str, str, str, str]:
        consumer_key = (self.settings.twitter_api_key or "").strip()
        consumer_secret = (self.settings.twitter_api_secret_key or "").strip()
        access_token = (self.settings.twitter_access_token or "").strip()
        access_token_secret = (self.settings.twitter_access_token_secret or "").strip()
        if not all((consumer_key, consumer_secret, access_token, access_token_secret)):
            raise ValueError(
                "Twitter OAuth 1.0a media upload is not fully configured. "
                "Set TWITTER_API_KEY, TWITTER_API_SECRET_KEY, TWITTER_ACCESS_TOKEN, and TWITTER_ACCESS_TOKEN_SECRET."
            )
        return consumer_key, consumer_secret, access_token, access_token_secret

    def _oauth1_headers(self, method: str, url: str, params: dict[str, str] | None = None) -> dict[str, str]:
        consumer_key, consumer_secret, access_token, access_token_secret = self._oauth1_credentials()
        oauth_params = {
            "oauth_consumer_key": consumer_key,
            "oauth_nonce": secrets.token_hex(16),
            "oauth_signature_method": "HMAC-SHA1",
            "oauth_timestamp": str(int(time.time())),
            "oauth_token": access_token,
            "oauth_version": "1.0",
        }
        signature_params = {**oauth_params, **(params or {})}
        normalized_pairs: list[tuple[str, str]] = []
        for key, value in signature_params.items():
            if value is None:
                continue
            if isinstance(value, (list, tuple)):
                values = value
            else:
                values = [value]
            for item in values:
                normalized_pairs.append(
                    (
                        quote(str(key), safe="~"),
                        quote(str(item), safe="~"),
                    )
                )
        normalized_pairs.sort()
        normalized = "&".join(f"{key}={value}" for key, value in normalized_pairs)
        signature_base = "&".join(
            [
                method.upper(),
                quote(url, safe="~"),
                quote(normalized, safe="~"),
            ]
        )
        signing_key = (
            f"{quote(consumer_secret, safe='~')}&{quote(access_token_secret, safe='~')}"
        )
        signature = base64.b64encode(
            hmac.new(signing_key.encode("utf-8"), signature_base.encode("utf-8"), hashlib.sha1).digest()
        ).decode("utf-8")
        oauth_params["oauth_signature"] = signature
        authorization = ", ".join(
            f'{quote(str(key), safe="~")}="{quote(str(value), safe="~")}"'
            for key, value in oauth_params.items()
        )
        return {"Authorization": f"OAuth {authorization}"}

    def _parse_data_url(self, value: str) -> tuple[str, bytes] | None:
        match = _DATA_URL_RE.match(value)
        if not match:
            return None
        try:
            raw = base64.b64decode(match.group("data"))
        except (binascii.Error, ValueError):
            return None
        return match.group("mime"), raw

    def _build_upload_filename(self, mime_type: str, source_url: str = "") -> str:
        extension = mimetypes.guess_extension(mime_type) or ""
        if extension == ".jpe":
            extension = ".jpg"
        if not extension and source_url:
            path = urlsplit(source_url).path
            if "." in path.rsplit("/", 1)[-1]:
                extension = "." + path.rsplit(".", 1)[-1].lower()
        return f"upload{extension or '.bin'}"

    async def _load_media_bytes(self, media_url: str) -> tuple[str, bytes, str]:
        parsed_data = self._parse_data_url(media_url)
        if parsed_data is not None:
            mime_type, raw_bytes = parsed_data
            return mime_type, raw_bytes, self._build_upload_filename(mime_type)

        resp = await self.client.get(media_url)
        resp.raise_for_status()
        mime_type = (resp.headers.get("Content-Type") or "application/octet-stream").split(";", 1)[0].strip()
        return mime_type, resp.content, self._build_upload_filename(mime_type, media_url)

    async def _get(self, path: str, params: dict | None = None) -> dict:
        resp = await self.client.get(
            f"{X_API_BASE}/{path.lstrip('/')}",
            headers=self._headers(),
            params=params or {},
        )
        data = resp.json()
        if resp.status_code >= 400:
            raise ValueError(_format_twitter_error("API", resp.status_code, data))
        return data

    async def _post(self, path: str, json: dict) -> dict:
        resp = await self.client.post(
            f"{X_API_BASE}/{path.lstrip('/')}",
            headers=self._headers(),
            json=json,
        )
        data = resp.json()
        if resp.status_code >= 400:
            raise ValueError(_format_twitter_error("API", resp.status_code, data))
        return data

    async def close(self):
        await self.client.aclose()

    async def get_me(self) -> dict:
        data = await self._get(
            "users/me",
            {
                "user.fields": "id,name,username,profile_image_url,public_metrics",
            },
        )
        return data.get("data", {})

    async def get_user_profile(self, user_id: str) -> dict:
        data = await self._get(
            f"users/{user_id}",
            {
                "user.fields": "id,name,username,profile_image_url,public_metrics",
            },
        )
        return data.get("data", {})

    async def get_user_tweets(self, user_id: str, max_results: int = 10) -> list[dict]:
        data = await self._get(
            f"users/{user_id}/tweets",
            {
                "max_results": max(5, min(max_results, 100)),
                "tweet.fields": "created_at,public_metrics",
                "exclude": "retweets,replies",
            },
        )
        return data.get("data", [])

    async def upload_media(self, raw_bytes: bytes, mime_type: str, filename: str) -> str:
        if not mime_type.startswith("image/"):
            raise ValueError("Twitter media publishing currently supports image uploads only.")
        media_data = base64.b64encode(raw_bytes).decode("utf-8")
        form_data = {
            "media_data": media_data,
            "media_category": "tweet_image",
        }
        headers = self._oauth1_headers(
            "POST",
            f"{X_UPLOAD_API_BASE}/media/upload.json",
            params=form_data,
        )
        resp = await self.client.post(
            f"{X_UPLOAD_API_BASE}/media/upload.json",
            headers=headers,
            data=form_data,
        )
        data = resp.json()
        if resp.status_code >= 400:
            raise ValueError(_format_twitter_error("media upload", resp.status_code, data))
        media_id = data.get("media_id_string") or str(data.get("media_id") or "")
        if not media_id:
            raise ValueError(f"Twitter media upload returned no media id: {data}")
        return media_id

    async def create_tweet(self, text: str = "", media_ids: list[str] | None = None) -> dict:
        payload: dict[str, object] = {}
        if text.strip():
            payload["text"] = text[:280]
        if media_ids:
            payload["media"] = {"media_ids": media_ids}
        if not payload:
            raise ValueError("Tweet text or media is required")
        data = await self._post("tweets", payload)
        return data.get("data", {})

    async def create_reply_tweet(self, tweet_id: str, text: str) -> dict:
        payload: dict[str, object] = {
            "text": text[:280],
            "reply": {"in_reply_to_tweet_id": tweet_id},
        }
        data = await self._post("tweets", payload)
        return data.get("data", {})

    async def create_tweet_with_media(self, text: str = "", media_urls: list[str] | None = None) -> dict:
        media_urls = media_urls or []
        if len(media_urls) > 4:
            raise ValueError("Twitter supports up to 4 images per tweet.")

        media_ids: list[str] = []
        for media_url in media_urls:
            mime_type, raw_bytes, filename = await self._load_media_bytes(media_url)
            media_ids.append(await self.upload_media(raw_bytes, mime_type, filename))

        return await self.create_tweet(text=text, media_ids=media_ids or None)
