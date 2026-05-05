"""Comment monitoring Celery task."""
from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.celery_app import celery_app
from core.kafka_client import get_kafka_producer
from loguru import logger


def _load_monitoring_models():
    try:
        from models.domain import SocialAccount, Post, PostStatus, Comment, Alert, AlertSeverity
    except ModuleNotFoundError:
        from backend.models.domain import SocialAccount, Post, PostStatus, Comment, Alert, AlertSeverity
    return SocialAccount, Post, PostStatus, Comment, Alert, AlertSeverity


def _load_nlp_pipeline():
    try:
        from services.nlp_pipeline import nlp_pipeline
    except ModuleNotFoundError:
        from backend.services.nlp_pipeline import nlp_pipeline
    return nlp_pipeline


@celery_app.task(name="services.comment_monitor.monitor_all_accounts")
def monitor_all_accounts():
    """Monitor comments and DMs for all active accounts."""
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    from core.config import get_settings

    SocialAccount, _, _, _, _, _ = _load_monitoring_models()
    settings = get_settings()

    engine = create_engine(settings.sync_database_url)
    with Session(engine) as session:
        accounts = session.execute(select(SocialAccount)).scalars().all()
        for account in accounts:
            monitor_account.delay(str(account.id))


@celery_app.task(name="services.comment_monitor.monitor_account")
def monitor_account(account_id: str):
    """Fetch and analyze comments for a specific account."""
    import asyncio
    import uuid
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    from core.config import get_settings

    SocialAccount, Post, PostStatus, Comment, Alert, AlertSeverity = _load_monitoring_models()
    nlp_pipeline = _load_nlp_pipeline()
    settings = get_settings()
    kafka_producer = get_kafka_producer()

    async def _run():
        engine = create_engine(settings.sync_database_url)
        with Session(engine) as session:
            account = session.get(SocialAccount, uuid.UUID(account_id))
            if not account:
                return

            posts = session.execute(
                select(Post).where(
                    Post.account_id == uuid.UUID(account_id),
                    Post.status == PostStatus.PUBLISHED,
                ).order_by(Post.published_at.desc()).limit(5)
            ).scalars().all()

            all_analyses = []
            for post in posts:
                comments = session.execute(
                    select(Comment).where(
                        Comment.post_id == post.id,
                        Comment.sentiment == None,  # noqa: E711
                    ).limit(20)
                ).scalars().all()

                for comment in comments:
                    analysis = await nlp_pipeline.process(comment.text)
                    text_lower = comment.text.lower()
                    is_question = "?" in comment.text
                    is_lead = any(token in text_lower for token in ["prix", "price", "combien", "commander", "buy", "devis"])
                    urgency = 1 + int(is_question) + int(analysis.is_toxic or analysis.is_spam) + int(analysis.sentiment == "negative")

                    comment.sentiment = analysis.sentiment
                    comment.sentiment_score = analysis.sentiment_score
                    comment.emotion = "anger" if analysis.is_toxic else ("curiosity" if is_question else "neutral")
                    comment.is_question = is_question
                    comment.is_lead = is_lead
                    comment.reply_priority = min(urgency, 4)
                    if analysis.is_spam or analysis.is_toxic:
                        comment.is_hidden = True

                    kafka_producer.emit_comment({
                        "comment_id": str(comment.id),
                        "post_id": str(comment.post_id),
                        "platform": account.platform.value,
                        "account_id": account_id,
                        "text": comment.text,
                        "author": getattr(comment, "author_username", None) or getattr(comment, "author_name", "") or "",
                        "timestamp": comment.created_at.isoformat() if getattr(comment, "created_at", None) else "",
                        "likes_count": getattr(comment, "likes_count", 0) or 0,
                        "is_reply": getattr(comment, "is_reply", False) or False,
                    })

                    kafka_producer.produce_event(
                        "social.nlp.results",
                        key=str(comment.id),
                        value={
                            "comment_id": str(comment.id),
                            "is_spam": analysis.is_spam,
                            "spam_score": analysis.spam_score,
                            "is_toxic": analysis.is_toxic,
                            "toxic_score": analysis.toxic_score,
                            "sentiment": analysis.sentiment,
                            "sentiment_score": analysis.sentiment_score,
                            "topic_id": analysis.topic_id,
                            "topic_label": analysis.topic_label,
                            "language": analysis.language,
                        },
                    )
                    all_analyses.append(analysis)

                session.commit()

            if all_analyses:
                negative_count = sum(1 for a in all_analyses if a.sentiment == "negative" or a.is_toxic)
                total = len(all_analyses)
                negative_ratio = negative_count / max(total, 1)
                volume_spike = total / 100.0
                detected = negative_ratio >= 0.5 and (volume_spike >= 2.0 or negative_count >= 15)
                if detected:
                    severity = "critical" if negative_ratio >= 0.75 or volume_spike >= 5.0 else "high"
                    alert = Alert(
                        id=uuid.uuid4(),
                        account_id=uuid.UUID(account_id),
                        severity=AlertSeverity.CRITICAL if severity == "critical" else AlertSeverity.HIGH,
                        alert_type="crisis_detected",
                        title=f"Crise detectee - {account.account_name}",
                        description=f"Crisis risk detected: {negative_count}/{total} negative comments, spike x{volume_spike:.1f}.",
                        metadata_={"negative_ratio": round(negative_ratio, 4), "volume_spike": round(volume_spike, 4)},
                    )
                    session.add(alert)
                    session.commit()
                    logger.warning(f"Crisis alert created for account {account_id}")

    asyncio.run(_run())
