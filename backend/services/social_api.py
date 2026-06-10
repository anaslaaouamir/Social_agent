import httpx
import logging
from models.domain import Platform

logger = logging.getLogger(__name__)

async def hide_comment_on_platform(platform: Platform, platform_comment_id: str, access_token: str) -> bool:
    """Hides a comment on Facebook or Instagram via the Graph API."""
    if platform == Platform.FACEBOOK:
        url = f"https://graph.facebook.com/v19.0/{platform_comment_id}"
        payload = {"is_hidden": True, "access_token": access_token}
    elif platform == Platform.INSTAGRAM:
        url = f"https://graph.facebook.com/v25.0/{platform_comment_id}"
        payload = {"hide": True, "access_token": access_token}
    else:
        logger.warning(f"Hiding comments on {platform} is not supported.")
        return False
        
    try:
        # Use a 10-second timeout so it never hangs infinitely
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            logger.info(f"Successfully hidden comment {platform_comment_id} on {platform}.")
            return True
    except Exception as e:
        logger.error(f"Failed to hide comment {platform_comment_id} on {platform}: {e}")
        return False