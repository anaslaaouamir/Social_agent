"""Content generation router — Module 2: captions, variants, A/B testing."""
from fastapi import APIRouter, Depends, HTTPException
from core.config import get_settings
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
):
    """
    Generate AI-powered captions and hashtags for a post (Module 2).
    Returns 3-5 variants optimized per platform in FR/AR/EN.
    """
    if not settings.anthropic_api_key:
        raise HTTPException(
            status_code=503,
            detail="ANTHROPIC_API_KEY not configured. Set it in .env to enable AI content generation."
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
    )
    return engine.to_dict(result)


@router.post("/generate-for-post/{post_id}")
async def generate_for_existing_post(
    post_id: str,
    payload: dict,
    current_user: User = Depends(get_current_user),
):
    """Generate content variants for an existing post and save them."""
    from sqlalchemy import select
    import uuid
    from core.database import AsyncSessionLocal
    from models.domain import Post, SocialAccount, PostStatus

    async with AsyncSessionLocal() as db:
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

    if not settings.anthropic_api_key:
        raise HTTPException(503, "ANTHROPIC_API_KEY not configured")

    try:
        engine = ContentGenerationEngine(anthropic_api_key=settings.anthropic_api_key)
        gen_result = await engine.generate(
            platform=Platform(platform_val.value),
            visual_description=payload.get("description", post.caption or ""),
            brand_name=payload.get("brand_name", ""),
            tone=ToneOfVoice(payload.get("tone", "brand")),
            languages=payload.get("languages", ["fr"]),
            num_variants=3,
        )

        # Save variants back to post
        async with AsyncSessionLocal() as db:
            p = await db.get(Post, uuid.UUID(post_id))
            if p:
                p.ai_caption_variants = engine.to_dict(gen_result)["captions"]
                p.ai_hashtag_suggestions = gen_result.hashtags[:15]
                await db.commit()

        return engine.to_dict(gen_result)
    except Exception as e:
        raise HTTPException(500, f"Generation failed: {e}")
