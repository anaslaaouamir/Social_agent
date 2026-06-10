"""
Pinterest API v5 Service
Handles user info, pin publishing, boards, and account metrics via Pinterest API v5.
"""
from __future__ import annotations

import httpx
from loguru import logger
from typing import Optional

PINTEREST_API_BASE = "https://api.pinterest.com/v5"


class PinterestGraphService:
    """Wrapper around the Pinterest API v5 for user-context operations."""

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
            f"{PINTEREST_API_BASE}/{path.lstrip('/')}",
            headers=self._headers(),
            params=params or {},
        )
        data = resp.json()
        if resp.status_code >= 400:
            raise ValueError(f"Pinterest API error {resp.status_code}: {data}")
        return data

    async def _post(self, path: str, json: dict) -> dict:
        resp = await self.client.post(
            f"{PINTEREST_API_BASE}/{path.lstrip('/')}",
            headers=self._headers(),
            json=json,
        )
        data = resp.json()
        if resp.status_code >= 400:
            raise ValueError(f"Pinterest API error {resp.status_code}: {data}")
        return data

    async def _delete(self, path: str) -> bool:
        resp = await self.client.delete(
            f"{PINTEREST_API_BASE}/{path.lstrip('/')}",
            headers=self._headers(),
        )
        return resp.status_code in (200, 204)

    async def _patch(self, path: str, json: dict) -> dict:
        resp = await self.client.patch(
            f"{PINTEREST_API_BASE}/{path.lstrip('/')}",
            headers=self._headers(),
            json=json,
        )
        data = resp.json()
        if resp.status_code >= 400:
            raise ValueError(f"Pinterest API error {resp.status_code}: {data}")
        return data

    async def close(self):
        await self.client.aclose()

    async def get_user_info(self) -> dict:
        """Fetch basic info about the authenticated Pinterest user."""
        data = await self._get("user_account")
        return data

    async def list_boards(self, page_size: int = 25, bookmark: str | None = None) -> dict:
        """List all boards for the authenticated user."""
        params = {"page_size": page_size}
        if bookmark:
            params["bookmark"] = bookmark
        data = await self._get("boards", params)
        return data

    async def create_board(self, name: str, description: str = "", privacy: str = "PUBLIC") -> dict:
        """Create a new board. privacy: PUBLIC | ALL_BOARDS_SECRET | SECRET"""
        data = await self._post("boards", {
            "name": name,
            "description": description,
            "privacy": privacy,
        })
        return data

    async def get_board(self, board_id: str) -> dict:
        """Get a specific board by ID."""
        data = await self._get(f"boards/{board_id}")
        return data

    async def update_board(self, board_id: str, name: str | None = None,
                           description: str | None = None, privacy: str | None = None) -> dict:
        """Update a board."""
        update_data = {}
        if name is not None:
            update_data["name"] = name
        if description is not None:
            update_data["description"] = description
        if privacy is not None:
            update_data["privacy"] = privacy
        data = await self._patch(f"boards/{board_id}", update_data)
        return data

    async def delete_board(self, board_id: str) -> bool:
        """Delete a board by ID."""
        return await self._delete(f"boards/{board_id}")

    async def list_board_pins(self, board_id: str, page_size: int = 25,
                              bookmark: str | None = None) -> dict:
        """List pins from a specific board."""
        params = {"page_size": page_size}
        if bookmark:
            params["bookmark"] = bookmark
        data = await self._get(f"boards/{board_id}/pins", params)
        return data

    async def list_user_pins(self, page_size: int = 25, bookmark: str | None = None) -> dict:
        """List all pins for the authenticated user."""
        params = {"page_size": page_size}
        if bookmark:
            params["bookmark"] = bookmark
        data = await self._get("pins", params)
        return data

    async def get_pin(self, pin_id: str) -> dict:
        """Get a specific pin by ID."""
        data = await self._get(f"pins/{pin_id}")
        return data

    async def create_pin(self, board_id: str, title: str,
                         description: str = "", media_url: str = "",
                         link: str = "", alt_text: str = "") -> dict:
        """Create a new pin on a board."""
        pin_data = {
            "board_id": board_id,
            "title": title,
            "description": description,
        }
        if media_url:
            pin_data["media_source"] = {
                "type": "image_url",
                "url": media_url,
            }
        if link:
            pin_data["link"] = link
        if alt_text:
            pin_data["alt_text"] = alt_text
        data = await self._post("pins", pin_data)
        return data

    async def update_pin(self, pin_id: str, title: str | None = None,
                         description: str | None = None, board_id: str | None = None,
                         link: str | None = None, alt_text: str | None = None) -> dict:
        """Update a pin."""
        update_data = {}
        if title is not None:
            update_data["title"] = title
        if description is not None:
            update_data["description"] = description
        if board_id is not None:
            update_data["board_id"] = board_id
        if link is not None:
            update_data["link"] = link
        if alt_text is not None:
            update_data["alt_text"] = alt_text
        data = await self._patch(f"pins/{pin_id}", update_data)
        return data

    async def delete_pin(self, pin_id: str) -> bool:
        """Delete a pin by ID."""
        return await self._delete(f"pins/{pin_id}")

    async def get_account_metrics(self, start_date: str, end_date: str) -> dict:
        """Get account-level analytics. Dates in YYYY-MM-DD."""
        data = await self._get("user_account/analytics", {
            "start_date": start_date,
            "end_date": end_date,
        })
        return data

    async def get_pin_analytics(self, pin_id: str, start_date: str, end_date: str) -> dict:
        """Get analytics for a specific pin."""
        data = await self._get(f"pins/{pin_id}/analytics", {
            "start_date": start_date,
            "end_date": end_date,
        })
        return data

    async def get_board_analytics(self, board_id: str, start_date: str, end_date: str) -> dict:
        """Get analytics for a specific board."""
        data = await self._get(f"boards/{board_id}/analytics", {
            "start_date": start_date,
            "end_date": end_date,
        })
        return data