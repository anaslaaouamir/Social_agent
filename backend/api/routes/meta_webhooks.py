"""Meta webhook verification and event intake."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, Response
from loguru import logger

from core.config import get_settings

router = APIRouter()
settings = get_settings()


@router.get("/meta")
async def verify_meta_webhook(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
):
    expected_token = (settings.meta_webhook_verify_token or "").strip()
    if hub_mode != "subscribe" or not expected_token or hub_verify_token != expected_token:
        logger.warning(
            "Meta webhook verification failed mode='{}' provided_token='{}' expected_configured={}",
            hub_mode,
            (hub_verify_token or "")[:12],
            bool(expected_token),
        )
        raise HTTPException(status_code=403, detail="Invalid webhook verification token")

    logger.info("Meta webhook verification succeeded")
    return Response(content=hub_challenge or "", media_type="text/plain")


@router.post("/meta")
async def receive_meta_webhook(request: Request):
    payload = await request.json()
    logger.info(
        "Meta webhook event received object='{}' entries={}",
        payload.get("object"),
        len(payload.get("entry") or []),
    )
    return {"status": "received"}
