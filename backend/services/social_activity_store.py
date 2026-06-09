"""Persist live social activity and create actionable alerts."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.domain import (
    Alert,
    AlertSeverity,
    Comment,
    ContentType,
    DirectMessage,
    Platform,
    Post,
    PostStatus,
    SentimentLabel,
)


def _as_uuid(value: str | uuid.UUID) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _sentiment_label(label: str | None, is_spam: bool = False, is_toxic: bool = False) -> SentimentLabel | None:
    if is_spam:
        return SentimentLabel.SPAM
    if is_toxic:
        return SentimentLabel.TOXIC
    if label in {"positive", "negative", "neutral"}:
        return SentimentLabel(label)
    return None


async def persist_live_post(
    db: AsyncSession,
    *,
    account_id: str | uuid.UUID,
    platform_post_id: str,
    content_type: str,
    text: str,
    media_url: str | None = None,
    published_at: float | None = None,
    likes: int = 0,
    comments_count: int = 0,
    shares_count: int = 0,
    reach: int = 0,
    impressions: int = 0,
) -> Post:
    """Create or update a DB post from a live platform post."""
    account_uuid = _as_uuid(account_id)
    result = await db.execute(
        select(Post).where(Post.account_id == account_uuid, Post.platform_post_id == platform_post_id)
    )
    post = result.scalar_one_or_none()
    if post is None:
        post = Post(
            id=uuid.uuid4(),
            account_id=account_uuid,
            content_type=ContentType(content_type) if content_type in ContentType._value2member_map_ else ContentType.IMAGE,
            status=PostStatus.PUBLISHED,
            caption=text or "",
            hashtags=[],
            media_urls=[media_url] if media_url else [],
            published_at=published_at,
            platform_post_id=platform_post_id,
        )
        db.add(post)
    else:
        post.caption = text or post.caption
        post.media_urls = [media_url] if media_url else post.media_urls
        post.published_at = published_at or post.published_at
        post.status = PostStatus.PUBLISHED

    post.likes_count = int(likes or 0)
    post.comments_count = int(comments_count or 0)
    post.shares_count = int(shares_count or 0)
    post.reach = int(reach or 0)
    post.impressions = int(impressions or 0)
    await db.flush()
    return post


async def persist_live_comment(
    db: AsyncSession,
    *,
    post: Post,
    comment: dict[str, Any],
    label: str,
    sentiment_score: float,
    is_spam: bool,
    is_toxic: bool,
    is_question: bool,
    is_lead: bool,
    reply_priority: int,
) -> Comment:
    """Create or update a DB comment from a live platform comment."""
    platform_comment_id = str(comment.get("id") or "").strip()
    if not platform_comment_id:
        platform_comment_id = f"{post.platform_post_id}:{uuid.uuid4()}"

    result = await db.execute(select(Comment).where(Comment.platform_comment_id == platform_comment_id))
    stored = result.scalar_one_or_none()
    if stored is None:
        stored = Comment(
            id=uuid.uuid4(),
            post_id=post.id,
            platform_comment_id=platform_comment_id,
            author_id=str(comment.get("author_id") or comment.get("author") or "unknown"),
            author_name=str(comment.get("author") or "Utilisateur"),
            text=str(comment.get("text") or ""),
        )
        db.add(stored)

    stored.post_id = post.id
    stored.author_name = str(comment.get("author") or stored.author_name or "Utilisateur")
    stored.text = str(comment.get("text") or stored.text or "")
    if label is not None or not getattr(stored, "sentiment", None):
        stored.sentiment = _sentiment_label(label, is_spam=is_spam, is_toxic=is_toxic)
        stored.sentiment_score = float(sentiment_score or 0.0)
        stored.emotion = "anger" if is_toxic or label == "negative" else ("curiosity" if is_question else "neutral")
        stored.is_hidden = bool(is_spam or is_toxic)
        
        stored.is_question = bool(is_question)
        stored.is_lead = bool(is_lead)
        stored.reply_priority = int(reply_priority or 0)
    stored.nlp_entities = {
        "source": "live_platform",
        "label": label,
        "is_spam": bool(is_spam),
        "is_toxic": bool(is_toxic),
    }
    await db.flush()
    return stored


async def persist_live_dm_item(db: AsyncSession, item: dict[str, Any]) -> DirectMessage:
    """Create or update a DB direct message/conversation preview."""
    account_uuid = _as_uuid(item["account_id"])
    sender_id = str(item.get("sender_id") or item.get("recipient_id") or item.get("id") or "unknown")
    message = str(item.get("message") or "")
    conversation_id = str(item.get("conversation_id") or item.get("id") or "")
    result = await db.execute(
        select(DirectMessage).where(
            DirectMessage.account_id == account_uuid,
            DirectMessage.sender_id == sender_id,
            DirectMessage.message == message,
        )
    )
    stored = result.scalar_one_or_none()
    if stored is None:
        stored = DirectMessage(
            id=uuid.uuid4(),
            account_id=account_uuid,
            sender_id=sender_id,
            sender_name=str(item.get("sender_name") or item.get("author") or "Client"),
            message=message,
        )
        db.add(stored)

    stored.sender_name = str(item.get("sender_name") or stored.sender_name or "Client")
    if str(item.get("label")) != "pending" or not getattr(stored, "intent", None):
        stored.intent = str(item.get("label") or item.get("intent") or "general")
        stored.sentiment_score = float(item.get("sentiment_score") or 0.0)
        stored.human_handoff = bool(item.get("label") in {"negative", "toxic"} or item.get("is_toxic"))
    stored.conversation_history = item.get("messages") or []
    stored.ai_response = conversation_id
    await db.flush()
    return stored


async def ensure_activity_alert(
    db: AsyncSession,
    *,
    account_id: str | uuid.UUID,
    severity: AlertSeverity,
    alert_type: str,
    title: str,
    description: str,
    metadata: dict[str, Any],
) -> Alert | None:
    """Create an alert unless an equivalent unacknowledged alert already exists."""
    account_uuid = _as_uuid(account_id)
    target_key = metadata.get("target_key")
    existing_result = await db.execute(
        select(Alert)
        .where(
            Alert.account_id == account_uuid,
            Alert.alert_type == alert_type,
            Alert.is_acknowledged == False,  # noqa: E712
        )
        .order_by(Alert.created_at.desc())
        .limit(100)
    )
    for alert in existing_result.scalars().all():
        if target_key and (alert.metadata_ or {}).get("target_key") == target_key:
            return None

    alert = Alert(
        id=uuid.uuid4(),
        account_id=account_uuid,
        severity=severity,
        alert_type=alert_type,
        title=title,
        description=description,
        metadata_=metadata,
    )
    db.add(alert)
    await db.flush()
    return alert


async def ensure_negative_comment_alert(
    db: AsyncSession,
    *,
    account_id: str | uuid.UUID,
    post: Post,
    comment: Comment,
    platform: Platform,
) -> None:
    await ensure_activity_alert(
        db,
        account_id=account_id,
        severity=AlertSeverity.HIGH if comment.sentiment == SentimentLabel.TOXIC else AlertSeverity.MEDIUM,
        alert_type="negative_comment",
        title="Commentaire negatif detecte",
        description=f"{comment.author_name}: {comment.text[:180]}",
        metadata={
            "target_kind": "comment",
            "target_key": str(comment.platform_comment_id),
            "account_id": str(account_id),
            "post_id": str(post.id),
            "platform_post_id": str(post.platform_post_id or ""),
            "comment_id": str(comment.id),
            "platform_comment_id": str(comment.platform_comment_id),
            "platform": platform.value,
            "action_url": f"/inbox?tab=posts&post={post.platform_post_id}&comment={comment.platform_comment_id}",
        },
    )


async def ensure_negative_dm_alert(
    db: AsyncSession,
    *,
    item: dict[str, Any],
) -> None:
    account_id = item["account_id"]
    conversation_id = str(item.get("conversation_id") or item.get("id") or "")
    sender_id = str(item.get("sender_id") or item.get("recipient_id") or "").strip()
    platform = str(item.get("platform") or "").strip()
    target_key = (
        f"dm:{account_id}:{platform}:conversation:{conversation_id}"
        if conversation_id
        else f"dm:{account_id}:{platform}:sender:{sender_id}"
    )
    await ensure_activity_alert(
        db,
        account_id=account_id,
        severity=AlertSeverity.HIGH if item.get("is_toxic") else AlertSeverity.MEDIUM,
        alert_type="negative_dm",
        title="DM negatif detecte",
        description=f"{item.get('sender_name') or 'Client'}: {str(item.get('message') or '')[:180]}",
        metadata={
            "target_kind": "dm",
            "target_key": target_key,
            "account_id": str(account_id),
            "conversation_id": conversation_id,
            "sender_id": sender_id,
            "dm_id": str(item.get("id") or ""),
            "platform": platform,
            "action_url": f"/inbox?tab=messages&dm={conversation_id or item.get('id') or ''}",
        },
    )
