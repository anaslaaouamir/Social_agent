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

                    if analysis.is_spam or analysis.is_toxic:
                        comment.is_hidden = True

                    if analysis.is_toxic or analysis.sentiment == "negative":
                        
                        alert = Alert(
                            id=uuid.uuid4(),
                            account_id=uuid.UUID(account_id),
                            severity=AlertSeverity.HIGH if analysis.is_toxic else AlertSeverity.MEDIUM,
                            alert_type="negative_comment",
                            title="Commentaire negatif detecte (Background)",
                            description=f"{comment.author_name}: {comment.text[:180]}",
                            metadata_={}
                        )
                        session.add(alert)

                    all_analyses.append(analysis)

                session.commit()

                        # --- NEW DM PROCESSING BLOCK ---
            try:
                from models.domain import DirectMessage
            except ModuleNotFoundError:
                from backend.models.domain import DirectMessage
            dms = session.execute(
                select(DirectMessage).where(
                    DirectMessage.account_id == uuid.UUID(account_id),
                    DirectMessage.intent == "pending",
                ).limit(20)
            ).scalars().all()
            for dm in dms:
                analysis = await nlp_pipeline.process(dm.message)
                dm.intent = "spam" if analysis.is_spam else "toxic" if analysis.is_toxic else analysis.sentiment
                dm.sentiment_score = analysis.sentiment_score
                dm.human_handoff = bool(dm.intent in {"negative", "toxic"})
                
                if dm.human_handoff:
                    alert = Alert(
                        id=uuid.uuid4(),
                        account_id=uuid.UUID(account_id),
                        severity=AlertSeverity.HIGH if analysis.is_toxic else AlertSeverity.MEDIUM,
                        alert_type="negative_dm",
                        title="DM negatif detecte (Background)",
                        description=f"{dm.sender_name}: {dm.message[:180]}",
                        metadata_={}
                    )
                    session.add(alert)
            session.commit()
            # --- END NEW DM PROCESSING BLOCK ---

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
