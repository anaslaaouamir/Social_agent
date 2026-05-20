"""Content generation router — Module 2: captions, variants, A/B testing."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from core.config import get_settings
from core.database import get_db
from models.domain import User
from api.auth_utils import get_current_user
from modules.content_generation import (
    ContentGenerationEngine, Platform, ToneOfVoice
)
from schemas.schemas import ContentGenerateRequest, ContentGenerateOut

router = APIRouter()
settings = get_settings()


@router.post("/generate", response_model=ContentGenerateOut)
async def generate_content(
    data: ContentGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate AI-powered captions and hashtags for a post (Module 2).
    Returns 3-5 variants optimized per platform in FR/AR/EN.
    """
    if not settings.anthropic_api_key and not settings.hugging_face_api:
        raise HTTPException(
            status_code=503,
            detail="ANTHROPIC_API_KEY or HUGGING_FACE_API not configured. Set one in .env to enable AI content generation."
        )

    try:
        platform = Platform(data.platform)
    except ValueError:
        raise HTTPException(400, f"Invalid platform: {data.platform}")

    try:
        tone = ToneOfVoice(data.tone)
    except ValueError:
        tone = ToneOfVoice.BRAND

    engine = ContentGenerationEngine(anthropic_api_key=settings.anthropic_api_key)
    result = await engine.generate(
        platform=platform,
        visual_description=data.visual_description,
        brand_name=data.brand_name,
        brand_guidelines=data.brand_guidelines,
        tone=tone,
        languages=data.languages,
        special_context=data.special_context,
        num_variants=data.num_variants,
        db=db,
        user_id=str(current_user.id),
        session_id=f"content:{current_user.id}:{data.platform}:{data.brand_name}",
    )
    return engine.to_dict(result)


@router.post("/generate-for-post/{post_id}")
async def generate_for_existing_post(
    post_id: str,
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate content variants for an existing post and save them."""
    from sqlalchemy import select
    import uuid
    from models.domain import Post, SocialAccount, PostStatus

    result = await db.execute(
        select(Post, SocialAccount.platform, SocialAccount.access_token)
        .join(SocialAccount)
        .where(
            Post.id == uuid.UUID(post_id),
            SocialAccount.user_id == current_user.id,
        )
    )
    row = result.first()
    if not row:
        raise HTTPException(404, "Post not found")

    post, platform_val, _ = row

    if not settings.anthropic_api_key and not settings.hugging_face_api:
        raise HTTPException(503, "ANTHROPIC_API_KEY or HUGGING_FACE_API not configured")

    try:
        engine = ContentGenerationEngine(anthropic_api_key=settings.anthropic_api_key)
        gen_result = await engine.generate(
            platform=Platform(platform_val.value),
            visual_description=payload.get("description", post.caption or ""),
            brand_name=payload.get("brand_name", ""),
            tone=ToneOfVoice(payload.get("tone", "brand")),
            languages=payload.get("languages", ["fr"]),
            num_variants=3,
            db=db,
            user_id=str(current_user.id),
            session_id=f"content-post:{post_id}",
        )

        # Save variants back to post
        p = await db.get(Post, uuid.UUID(post_id))
        if p:
            p.ai_caption_variants = engine.to_dict(gen_result)["captions"]
            p.ai_hashtag_suggestions = gen_result.hashtags[:15]

        return engine.to_dict(gen_result)
    except Exception as e:
        raise HTTPException(500, f"Generation failed: {e}")
