"""Hashtag intelligence router."""
from collections import Counter
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from models.domain import SocialAccount, User
from api.auth_utils import get_current_user
from api.routes.posts import _fetch_live_posts_for_account
from modules.hashtag_intelligence import HashtagIntelligenceSystem
from services.llm_orchestrator import LLMConfigurationError, LLMRequest, get_llm_orchestrator

router = APIRouter()
_system = HashtagIntelligenceSystem()


def _normalize_hashtag(tag: str) -> str:
    cleaned = re.sub(r"[^\w\u0600-\u06ff_]", "", str(tag or "").strip())
    if not cleaned:
        return ""
    return cleaned if cleaned.startswith("#") else f"#{cleaned}"


def _extract_hashtags(text: str) -> list[str]:
    return [
        _normalize_hashtag(tag)
        for tag in re.findall(r"#[\w\u0600-\u06ff_]+", str(text or ""))
        if _normalize_hashtag(tag)
    ]


async def _connected_accounts_for_platform(
    db: AsyncSession,
    user_id,
    platform: str,
) -> list[SocialAccount]:
    result = await db.execute(
        select(SocialAccount).where(SocialAccount.user_id == user_id)
    )
    accounts = list(result.scalars().all())
    if platform and platform != "all":
        accounts = [account for account in accounts if account.platform.value == platform]
    return accounts


async def _get_live_platform_hashtag_trends(
    db: AsyncSession,
    current_user: User,
    platform: str,
    limit_per_account: int = 20,
) -> list[dict]:
    """Build platform trend context from hashtags observed in live account posts."""
    accounts = await _connected_accounts_for_platform(db, current_user.id, platform)
    counter: Counter[str] = Counter()
    engagement: dict[str, float] = {}

    for account in accounts:
        try:
            posts = await _fetch_live_posts_for_account(account, limit=limit_per_account)
        except Exception:
            continue
        for post in posts:
            tags = _extract_hashtags(str(post.get("text") or ""))
            weight = 1 + float(post.get("likes") or 0) + float(post.get("comments_count") or 0) * 2 + float(post.get("shares_count") or 0) * 3
            for tag in tags:
                key = tag.lower()
                counter[key] += 1
                engagement[key] = engagement.get(key, 0.0) + weight

    trends = []
    for key, count in counter.most_common(30):
        score = min(100.0, 40 + count * 10 + engagement.get(key, 0.0) ** 0.5)
        trends.append(
            {
                "tag": key if key.startswith("#") else f"#{key}",
                "score": round(score, 2),
                "post_count": int(count),
                "engagement_weight": round(engagement.get(key, 0.0), 2),
                "source": "observed_live_posts",
            }
        )
    return trends


@router.post("/recommend")
async def recommend_hashtags(payload: dict, current_user: User = Depends(get_current_user)):
    """Get AI-powered hashtag recommendations (Module 3)."""
    rec = await _system.recommend(
        caption=payload.get("caption", ""),
        platform=payload.get("platform", "instagram"),
        category=payload.get("category", "lifestyle"),
        brand_hashtags=payload.get("brand_hashtags", []),
        languages=payload.get("languages", ["fr"]),
        n_hashtags=int(payload.get("n_hashtags", 25)),
    )
    return _system.to_dict(rec)


@router.post("/generate")
async def generate_hashtags(
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate hashtags with the central LLM using live API trends as context."""
    caption = str(payload.get("caption") or payload.get("topic") or "").strip()
    topic = str(payload.get("topic") or caption).strip()
    platform = str(payload.get("platform") or "instagram").strip().lower()
    n_hashtags = max(1, min(int(payload.get("n_hashtags", 8)), 30))
    if not caption:
        raise HTTPException(400, "caption or topic is required")

    live_trends = await _get_live_platform_hashtag_trends(db, current_user, platform)
    if not live_trends:
        raise HTTPException(
            404,
            "Aucune tendance hashtag live disponible via les APIs des comptes connectes.",
        )

    trend_context = live_trends[:20]
    system_prompt = (
        "Tu es un expert hashtags social media pour le marche marocain et international. "
        "Tu generes des hashtags avec le LLM, mais uniquement a partir du caption et des "
        "tendances live fournies depuis les APIs des comptes connectes. "
        "Tu retournes uniquement du JSON valide, sans markdown."
    )
    prompt = f"""Genere exactement {n_hashtags} hashtags optimises pour {platform}.

Caption:
{caption}

Sujet:
{topic}

Tendances live API disponibles:
{trend_context}

Regles:
- utilise les tendances live si elles sont pertinentes pour le caption
- ignore les tendances non pertinentes meme si elles ont un bon score
- mix de hashtags larges, moyens, niche et locaux si pertinent
- evite les hashtags bannis, spammy ou follow/like bait

Retourne uniquement ce JSON:
{{"hashtags":["#tag1","#tag2"],"performance_score":75,"trend_sources":["observed_live_posts"]}}"""

    try:
        data = await get_llm_orchestrator().generate_json(
            LLMRequest(
                user_message=prompt,
                system_prompt=system_prompt,
                user_id=str(current_user.id),
                session_id=f"hashtags:{current_user.id}:{platform}:{topic}",
                feature="hashtag_generation",
                persist_memory=True,
                metadata={"topic": topic, "caption": caption, "platform": platform, "trend_context": trend_context},
                max_tokens=800,
            ),
            db=db,
        )
    except LLMConfigurationError as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Hashtag generation failed: {exc}") from exc

    hashtags = [
        _normalize_hashtag(str(tag))
        for tag in data.get("hashtags", [])
        if _normalize_hashtag(str(tag))
    ][:n_hashtags]
    return {
        "hashtags": hashtags,
        "performance_score": int(data.get("performance_score") or 75),
        "trend_context": trend_context,
        "trend_sources": data.get("trend_sources") or ["observed_live_posts"],
    }


@router.get("/trending")
async def get_trending(
    platform: str = "instagram",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get hashtag trends only from live connected platform APIs."""
    return (await _get_live_platform_hashtag_trends(db, current_user, platform))[:20]
