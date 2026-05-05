"""Comments analysis and moderation router."""
from __future__ import annotations
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.database import get_db
from models.domain import User, Comment, Post, SocialAccount, SentimentLabel
from api.auth_utils import get_current_user
from services.nlp_pipeline import nlp_pipeline

router = APIRouter()


def _priority_from_result(result) -> int:
    priority = 1
    if "?" in result.text:
        priority += 1
    if result.is_spam or result.is_toxic:
        priority += 2
    if result.sentiment == "negative":
        priority += 1
    return min(priority, 4)


def _analysis_to_dict(result) -> dict:
    text_lower = result.text.lower()
    is_question = "?" in result.text
    is_lead = any(token in text_lower for token in ["prix", "price", "combien", "commander", "buy", "devis"])
    priority = _priority_from_result(result)
    return {
        "text": result.text,
        "language": result.language,
        "sentiment": result.sentiment,
        "sentiment_score": result.sentiment_score,
        "emotion": "anger" if result.is_toxic else ("curiosity" if is_question else ("joy" if result.sentiment == "positive" else "neutral")),
        "is_question": is_question,
        "is_lead": is_lead,
        "is_toxic": result.is_toxic,
        "is_spam": result.is_spam,
        "reply_priority": priority,
        "urgency_score": priority,
        "entities": [],
        "topics": result.topic_keywords or ([result.topic_label] if result.topic_label not in {"uncategorized", "empty", "error"} else []),
        "suggested_reply": "" if result.is_spam else "Merci pour votre message. Nous revenons vers vous rapidement.",
        "auto_hide": result.is_spam or result.is_toxic,
    }


def _detect_crisis(analyses: list[dict], baseline_volume: int) -> dict:
    total = len(analyses)
    if total == 0:
        return {
            "detected": False,
            "severity": "none",
            "negative_ratio": 0.0,
            "volume_spike": 0.0,
            "alert_message": "",
        }
    negative_count = sum(1 for item in analyses if item["sentiment"] == "negative" or item["is_toxic"])
    negative_ratio = negative_count / total
    volume_spike = total / max(float(baseline_volume), 1.0)
    detected = negative_ratio >= 0.5 and (volume_spike >= 2.0 or negative_count >= 15)
    severity = "none"
    if detected:
        severity = "critical" if negative_ratio >= 0.75 or volume_spike >= 5.0 else "high"
    return {
        "detected": detected,
        "severity": severity,
        "negative_ratio": round(negative_ratio, 4),
        "volume_spike": round(volume_spike, 4),
        "alert_message": (
            f"Crisis risk detected: {negative_count}/{total} negative comments, spike x{volume_spike:.1f}."
            if detected else ""
        ),
    }


@router.post("/analyze")
async def analyze_comment(payload: dict, current_user: User = Depends(get_current_user)):
    """Analyze a single comment with the shared NLP pipeline."""
    result = await nlp_pipeline.process(payload.get("text", ""))
    return _analysis_to_dict(result)


@router.post("/analyze-batch")
async def analyze_batch(payload: dict, current_user: User = Depends(get_current_user)):
    """Analyze multiple comments for crisis detection."""
    texts = payload.get("texts", [])
    if not texts:
        raise HTTPException(400, "texts list required")
    analyses = [_analysis_to_dict(await nlp_pipeline.process(text)) for text in texts[:100]]
    crisis = _detect_crisis(analyses, baseline_volume=payload.get("baseline_volume", 100))
    return {
        "analyses": analyses,
        "crisis": crisis,
        "summary": {
            "total": len(analyses),
            "positive": sum(1 for a in analyses if a["sentiment"] == "positive"),
            "negative": sum(1 for a in analyses if a["sentiment"] == "negative"),
            "toxic": sum(1 for a in analyses if a["is_toxic"]),
            "spam": sum(1 for a in analyses if a["is_spam"]),
            "leads": sum(1 for a in analyses if a["is_lead"]),
            "questions": sum(1 for a in analyses if a["is_question"]),
        },
    }


@router.get("/")
async def list_comments(
    post_id: str = Query(...),
    priority: str = Query(None),
    limit: int = Query(50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List stored comments for a post."""
    q = select(Comment).join(Post).join(SocialAccount).where(
        Comment.post_id == uuid.UUID(post_id),
        SocialAccount.user_id == current_user.id,
    )
    if priority:
        q = q.where(Comment.reply_priority == priority)
    q = q.order_by(Comment.reply_priority.desc(), Comment.created_at.desc()).limit(limit)
    result = await db.execute(q)
    comments = result.scalars().all()
    return [
        {
            "id": str(c.id),
            "label": (
                "spam" if c.sentiment == SentimentLabel.SPAM else
                "toxic" if c.sentiment == SentimentLabel.TOXIC else
                (c.sentiment.value if c.sentiment else "neutral")
            ),
            "label_color": {
                "spam": "gray",
                "toxic": "red",
                "positive": "green",
                "negative": "orange",
                "neutral": "blue",
            }.get(
                "spam" if c.sentiment == SentimentLabel.SPAM else
                "toxic" if c.sentiment == SentimentLabel.TOXIC else
                (c.sentiment.value if c.sentiment else "neutral"),
                "blue",
            ),
            "author_name": c.author_name,
            "text": c.text,
            "sentiment": c.sentiment.value if c.sentiment else None,
            "sentiment_score": c.sentiment_score,
            "emotion": c.emotion,
            "is_question": c.is_question,
            "is_lead": c.is_lead,
            "reply_priority": c.reply_priority,
            "auto_replied": c.auto_replied,
            "auto_reply_text": c.auto_reply_text,
            "is_hidden": c.is_hidden,
        }
        for c in comments
    ]


@router.get("/feed")
async def labeled_comment_feed(
    account_id: str = Query(None),
    label_filter: str = Query(None, description="spam|toxic|positive|negative|neutral"),
    limit: int = Query(50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Flux de commentaires en temps reel avec labels NLP visibles."""
    q = (
        select(Comment, SocialAccount.platform)
        .join(Post, Comment.post_id == Post.id)
        .join(SocialAccount, Post.account_id == SocialAccount.id)
        .where(SocialAccount.user_id == current_user.id)
    )
    if account_id:
        q = q.where(SocialAccount.id == uuid.UUID(account_id))
    if label_filter == "spam":
        q = q.where(Comment.sentiment == SentimentLabel.SPAM)
    elif label_filter == "toxic":
        q = q.where(Comment.sentiment == SentimentLabel.TOXIC)
    elif label_filter in ("positive", "negative", "neutral"):
        q = q.where(Comment.sentiment == SentimentLabel(label_filter))

    q = q.order_by(Comment.reply_priority.desc(), Comment.created_at.desc()).limit(limit)
    result = await db.execute(q)
    rows = result.all()

    items = []
    for comment, platform in rows:
        label = (
            "spam" if comment.sentiment == SentimentLabel.SPAM else
            "toxic" if comment.sentiment == SentimentLabel.TOXIC else
            (comment.sentiment.value if comment.sentiment else "neutral")
        )
        items.append({
            "id": str(comment.id),
            "author": comment.author_name,
            "text": comment.text,
            "label": label,
            "sentiment_score": comment.sentiment_score,
            "priority": comment.reply_priority,
            "platform": platform.value if platform else None,
            "auto_hide": comment.is_hidden,
            "suggested_reply": comment.auto_reply_text or "",
            "created_at": comment.created_at.isoformat() if comment.created_at else None,
        })

    return {
        "total": len(items),
        "label_filter": label_filter,
        "items": items,
    }
