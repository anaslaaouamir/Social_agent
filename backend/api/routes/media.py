"""Media upload and AI analysis endpoint."""
from __future__ import annotations
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from core.config import get_settings
from models.domain import User
from api.auth_utils import get_current_user
from modules.computer_vision import ComputerVisionModule

router = APIRouter()
settings = get_settings()


@router.post("/analyze")
async def analyze_media(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Upload media and run full AI analysis (Module 1)."""
    allowed = {"image/jpeg", "image/png", "image/webp", "video/mp4", "video/quicktime"}
    if file.content_type not in allowed:
        raise HTTPException(400, f"Unsupported media type: {file.content_type}")

    max_size = 50 * 1024 * 1024  # 50MB
    data = await file.read()
    if len(data) > max_size:
        raise HTTPException(413, "File too large (max 50MB)")

    module = ComputerVisionModule(anthropic_api_key=settings.anthropic_api_key)
    result = await module.analyze(data, filename=file.filename or "upload")
    return module.to_dict(result)


@router.post("/analyze-url")
async def analyze_media_url(
    payload: dict,
    current_user: User = Depends(get_current_user),
):
    """Analyze media from URL."""
    url = payload.get("url")
    if not url:
        raise HTTPException(400, "url is required")

    import httpx
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.content

    filename = url.split("/")[-1] or "image.jpg"
    module = ComputerVisionModule(anthropic_api_key=settings.anthropic_api_key)
    result = await module.analyze(data, filename=filename)
    return module.to_dict(result)
