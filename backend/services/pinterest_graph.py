"""
Pinterest API Service
Fetches real data: boards, pins, analytics.
Publishes pins to boards.
"""
from __future__ import annotations
import httpx
from typing import Optional
from loguru import logger
from core.config import get_settings

class PinterestGraphService:
    """Wrapper for the Pinterest V5 API."""

    def __init__(self, access_token: str):
        self.token = access_token
        self.settings = get_settings()
        self.is_sandbox = bool(self.settings.pinterest_access_token and self.token == self.settings.pinterest_access_token)
        self.base_url = "https://api-sandbox.pinterest.com/v5" if self.is_sandbox else "https://api.pinterest.com/v5"
        
        self.client = httpx.AsyncClient(timeout=30)
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    async def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self.base_url}/{path.lstrip('/')}"
        resp = await self.client.get(url, headers=self.headers, params=params)
        data = resp.json()
        if resp.status_code >= 400:
            raise ValueError(f"Pinterest API error: {data.get('message', 'Unknown error')} - {data.get('code')}")
        return data

    async def _post(self, path: str, json: dict) -> dict:
        url = f"{self.base_url}/{path.lstrip('/')}"
        resp = await self.client.post(url, headers=self.headers, json=json)
        data = resp.json()
        if resp.status_code >= 400:
            raise ValueError(f"Pinterest API error: {data.get('message', 'Unknown error')}")
        return data

    async def close(self):
        await self.client.aclose()

    # ------------------------------------------------------------------ #
    # Boards & Pins                                                      #
    # ------------------------------------------------------------------ #
    async def get_boards(self) -> list[dict]:
        """Returns all boards for the authenticated user."""
        try:
            data = await self._get("boards")
            return data.get("items", [])
        except Exception as e:
            logger.error(f"Failed to fetch Pinterest boards: {e}")
            return []

    async def get_pins(self) -> list[dict]:
        """Returns pins for the authenticated user."""
        try:
            data = await self._get("pins")
            return data.get("items", [])
        except Exception as e:
            logger.error(f"Failed to fetch Pinterest pins: {e}")
            return []

    async def create_pin(self, board_id: str, title: str, description: str, image_url: str, link: Optional[str] = None) -> dict:
        """Publishes a new pin with an image URL to a specific board."""
        payload = {
            "board_id": board_id,
            "title": title,
            "description": description,
            "media_source": {
                "source_type": "image_url",
                "url": image_url
            }
        }
        if link:
            payload["link"] = link
            
        return await self._post("pins", json=payload)

    # ------------------------------------------------------------------ #
    # Analytics                                                          #
    # ------------------------------------------------------------------ #
    async def get_pin_analytics(self, pin_id: str, start_date: str, end_date: str) -> dict:
        """
        Returns analytics for a specific pin.
        Dates should be in YYYY-MM-DD format.
        """
        metric_types = "IMPRESSION,SAVE,PIN_CLICK,OUTBOUND_CLICK"
        try:
            data = await self._get(
                f"pins/{pin_id}/analytics",
                params={
                    "start_date": start_date,
                    "end_date": end_date,
                    "metric_types": metric_types
                }
            )
            # data has the structure {"all": {"summary_metrics": {...}, "daily_metrics": [...]}}
            all_metrics = data.get("all", {})
            summary = all_metrics.get("summary_metrics", {})
            return {
                "impressions": summary.get("IMPRESSION", 0),
                "saves": summary.get("SAVE", 0),
                "clicks": summary.get("PIN_CLICK", 0),
                "outbound_clicks": summary.get("OUTBOUND_CLICK", 0)
            }
        except Exception as e:
            # Downgraded to debug to avoid log spam for pins the user doesn't own
            logger.debug(f"Failed to fetch analytics for pin {pin_id}: {e}")
            return {}
