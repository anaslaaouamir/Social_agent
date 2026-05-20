"""Routes NLP : analyse manuelle, feed unifie, entrainement engagement et RAG."""
from __future__ import annotations

import logging
import os
import re
import tempfile
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth_utils import get_current_user
from core.database import get_db
from models.domain import AlertSeverity, Comment, Post, SentimentLabel, SocialAccount, User
from services.dataset_loader import load_instagram_dataset
from services.ml_engagement import engagement_predictor
from services.nlp_pipeline import nlp_pipeline
from services.rag_service import get_rag_service
from services.social_activity_store import ensure_activity_alert

router = APIRouter()
logger = logging.getLogger(__name__)


class NLPRequest(BaseModel):
    text: str


class EngagementRequest(BaseModel):
    platform: str
    content_type: str
    hour: int
    day_of_week: int
    caption_length: int = 150
    hashtag_count: int = 10
    has_emoji: bool = True
    has_mention: bool = False
    has_question: bool = False
    followers: int = 10000
    historical_avg_er: float = 0.03


class RAGChatRequest(BaseModel):
    message: str
    history: list[dict] = Field(default_factory=list)
    brand_name: str = "Notre Marque"
    language: str = "fr"
    brand_knowledge: str = ""


class RAGTextRequest(BaseModel):
    name: str
    text: str


class AutoReplyRequest(BaseModel):
    message_id: str
    content: str
    platform: str
    type: str
    brand_name: str = "Notre Marque"
    language: str = "auto"
    confidence_threshold: float = 0.6
    fallback_templates: dict[str, str] = Field(default_factory=dict)
    account_id: str | None = None
    recipient_id: str | None = None
    reply_mode: str | None = None
    reply_target_id: str | None = None
    reply_parent_id: str | None = None


def _language_label(language: str) -> str:
    return (
        "francais" if language == "fr"
        else "arabe" if language == "ar"
        else "anglais" if language == "en"
        else "darija" if language == "darija"
        else language
    )


def _normalize_detected_language(text: str, detected: str) -> str:
    lowered = text.lower()
    darija_markers = [
        r"\b(bghit|bghiti|khasni|wach|chno|fin|mzyan|bzaf|safi|hadi|hadchi|dyal|dial|ana|nta|nti)\b",
        r"\b(3afak|7it|9der|mabghitch|ma\s+bghit|kifach)\b",
    ]
    if any(re.search(pattern, lowered) for pattern in darija_markers):
        return "darija"
    if re.search(r"[\u0600-\u06ff]", text):
        return "ar"
    if detected in {"fr", "ar", "en"}:
        return detected
    return "fr"



def _fallback_template_for_language(language: str, templates: dict[str, str]) -> str:
    default_templates = {
        "fr": "Merci pour votre message. Notre equipe vous repondra dans les plus brefs delais.",
        "ar": "\u0634\u0643\u0631\u0627 \u0639\u0644\u0649 \u0631\u0633\u0627\u0644\u062a\u0643. \u0633\u064a\u0631\u062f \u0639\u0644\u064a\u0643 \u0641\u0631\u064a\u0642\u0646\u0627 \u0641\u064a \u0623\u0642\u0631\u0628 \u0648\u0642\u062a.",
        "darija": "\u0634\u0643\u0631\u0627 \u0639\u0644\u0649 \u0627\u0644\u0631\u0633\u0627\u0644\u0629 \u062f\u064a\u0627\u0644\u0643. \u0627\u0644\u0641\u0631\u064a\u0642 \u062f\u064a\u0627\u0644\u0646\u0627 \u063a\u0627\u062f\u064a \u064a\u062c\u0627\u0648\u0628\u0643 \u0641\u0627\u0642\u0631\u0628 \u0648\u0642\u062a.",
        "en": "Thank you for your message. Our team will get back to you shortly.",
    }
    return (
        templates.get(language)
        or templates.get("fr")
        or default_templates.get(language)
        or default_templates["fr"]
    )


def _reply_requires_team_review(reply: str) -> bool:
    lowered = reply.lower()
    markers = [
        "service client",
        "transmets",
        "transmet",
        "equipe vous repondra",
        "équipe vous répondra",
        "devis",
        "consultation",
        "je n'ai pas d'informations",
        "je ne dispose pas",
    ]
    return any(marker in lowered for marker in markers)


def _human_review_alert_text(
    *,
    item_type: str,
    platform: str,
    message: str,
    reply: str,
    confidence: float,
    threshold: float,
) -> tuple[str, str]:
    channel = "DM" if item_type == "dm" else "commentaire"
    message_preview = message.strip().replace("\n", " ")[:220]
    reply_preview = reply.strip().replace("\n", " ")[:220]
    title = f"Revue humaine requise - {channel} {platform}"
    description = (
        f"Le RAG a repondu mais demande une verification equipe. "
        f"Message client: \"{message_preview}\". "
        f"Reponse envoyee: \"{reply_preview}\". "
        f"Score RAG {confidence:.2f}, seuil {threshold:.2f}."
    )
    return title, description


@router.post("/analyze")
async def analyze_text(req: NLPRequest, current_user: User = Depends(get_current_user)):
    """Analyse complete NLP d'un texte."""
    result = await nlp_pipeline.process(req.text)
    return {
        "text": result.text,
        "label": nlp_pipeline.get_unified_label(result),
        "spam": {"is_spam": result.is_spam, "score": result.spam_score},
        "toxic": {"is_toxic": result.is_toxic, "score": result.toxic_score},
        "sentiment": {"label": result.sentiment, "score": result.sentiment_score},
        "topic": {"id": result.topic_id, "label": result.topic_label, "keywords": result.topic_keywords},
        "language": result.language,
    }


@router.post("/predict-engagement")
async def predict_engagement(req: EngagementRequest, current_user: User = Depends(get_current_user)):
    """Predit l'engagement d'un post avant publication."""
    pred = engagement_predictor.predict(
        platform=req.platform,
        content_type=req.content_type,
        hour=req.hour,
        day_of_week=req.day_of_week,
        caption_length=req.caption_length,
        hashtag_count=req.hashtag_count,
        has_emoji=req.has_emoji,
        has_mention=req.has_mention,
        has_question=req.has_question,
        followers=req.followers,
        historical_avg_er=req.historical_avg_er,
    )
    return {
        "predicted_engagement_rate": pred.predicted_engagement_rate,
        "feature_importance": pred.feature_importance,
    }


@router.get("/feed")
async def labeled_feed(
    source: str = Query("all", description="all|comments|dms"),
    label: str = Query(None, description="positive|negative|neutral|spam|toxic"),
    limit: int = Query(50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Flux unifie commentaires + DMs avec labels NLP."""
    items = []

    if source in ("all", "comments"):
        q = (
            select(Comment)
            .join(Post, Comment.post_id == Post.id)
            .join(SocialAccount, Post.account_id == SocialAccount.id)
            .where(SocialAccount.user_id == current_user.id)
        )
        if label == "spam":
            q = q.where(Comment.sentiment == SentimentLabel.SPAM)
        elif label == "toxic":
            q = q.where(Comment.sentiment == SentimentLabel.TOXIC)
        elif label in ("positive", "negative", "neutral"):
            q = q.where(Comment.sentiment == SentimentLabel(label))
        q = q.order_by(Comment.created_at.desc()).limit(limit)
        result = await db.execute(q)
        comments = result.scalars().all()
        for comment in comments:
            lbl = (
                "spam" if comment.sentiment == SentimentLabel.SPAM else
                "toxic" if comment.sentiment == SentimentLabel.TOXIC else
                (comment.sentiment.value if comment.sentiment else "neutral")
            )
            items.append({
                "source_type": "comment",
                "id": str(comment.id),
                "author": comment.author_name,
                "text": comment.text,
                "label": lbl,
                "sentiment_score": comment.sentiment_score,
                "is_spam": comment.sentiment == SentimentLabel.SPAM,
                "is_toxic": comment.sentiment == SentimentLabel.TOXIC,
                "reply_priority": comment.reply_priority,
                "created_at": comment.created_at.isoformat() if comment.created_at else None,
            })

    items.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return {
        "total": len(items),
        "label_filter": label,
        "source": source,
        "items": items[:limit],
    }


@router.post("/train-engagement")
async def train_engagement_model(
    payload: dict,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    """Lance l'entrainement du modele d'engagement en tache de fond."""

    def _train():
        ig_df = load_instagram_dataset()
        if ig_df is None or ig_df.empty:
            raise RuntimeError("Dataset Instagram Analytics introuvable ou vide")
        metrics = engagement_predictor.train_on_dataset(ig_df)
        logger.info("Training termine: %s", metrics)

    background_tasks.add_task(_train)
    return {"status": "training_started", "message": "Modele en cours d'entrainement"}


@router.post("/rag/chat")
async def rag_chat(
    req: RAGChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Discute avec le chatbot RAG via la base de connaissances serveur."""
    language_label = (
        "francais" if req.language == "fr"
        else "arabe" if req.language == "ar"
        else "anglais" if req.language == "en"
        else req.language
    )
    system_context = (
        f"Tu es l'assistant IA de la marque \"{req.brand_name}\". "
        f"Reponds en {language_label}. "
        "Reponds de facon naturelle, chaleureuse et professionnelle. "
        "Si le contexte est insuffisant, dis poliment que tu transmets au service client."
    )
    if req.brand_knowledge.strip():
        system_context = f"{system_context}\n\nContexte de marque additionnel:\n{req.brand_knowledge.strip()}"

    try:
        reply = await get_rag_service().chat_with_rag(
            user_message=req.message,
            conversation_history=req.history,
            system_context=system_context,
            db=db,
            user_id=str(current_user.id),
            session_id=f"rag:{current_user.id}:{req.brand_name}",
        )
    except Exception as exc:
        logger.warning("RAG chat error: %s", exc)
        reply = (
            "Je n ai pas pu generer une reponse complete pour le moment. "
            "Je transmets votre demande au service client."
        )
    lowered = reply.lower()
    requires_human = "service client" in lowered or "transmet" in lowered
    return {
        "message": reply,
        "intent": "customer_support",
        "requires_human": requires_human,
    }


@router.post("/rag-autoreply")
async def rag_autoreply(
    req: AutoReplyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a RAG auto-reply for an incoming DM or comment.

    Platform delivery is intentionally not forced here because this compact request
    does not include the account token, reply mode, and target identifiers needed
    to post safely on every network.
    """
    item_type = req.type.lower().strip()
    if item_type not in {"dm", "comment"}:
        return {"message_id": req.message_id, "reply": "", "delivery_status": "invalid_type"}

    rag = get_rag_service()
    context_docs = rag.retrieve(req.content, n_results=4)
    context_text = "\n".join(d["text"] for d in context_docs if d.get("text"))
    raw_detected_language = nlp_pipeline.detect_language(req.content)
    detected_language = _normalize_detected_language(req.content, raw_detected_language)
    language = detected_language if req.language == "auto" else req.language
    language_label = _language_label(language)
    max_relevance = max((float(doc.get("relevance") or 0.0) for doc in context_docs), default=0.0)
    requires_human = max_relevance < float(req.confidence_threshold)
    system_context = (
        f"Tu es l'assistant IA de la marque \"{req.brand_name}\". "
        f"Reponds en {language_label}. "
        "Reponds de facon courte, utile et non promotionnelle. "
        "Si la base de connaissance ne suffit pas, dis que tu transmets au service client."
    )
    if context_text:
        system_context = f"{system_context}\n\nBase de connaissance:\n{context_text}"

    if requires_human:
        reply = _fallback_template_for_language(language, req.fallback_templates)
    else:
        try:
            reply = await rag.chat_with_rag(
                req.content,
                [],
                system_context,
                db=db,
                user_id=str(current_user.id),
                session_id=f"rag-autoreply:{current_user.id}:{item_type}:{req.message_id}",
            )
        except Exception as exc:
            logger.warning("RAG auto-reply error: %s", exc)
            requires_human = True
            reply = _fallback_template_for_language(language, req.fallback_templates)

    delivery_status = "generated_only"
    platform_result = None
    if req.account_id and reply:
        try:
            from api.routes.dm import _send_unified_reply

            account_result = await db.execute(
                select(SocialAccount).where(
                    SocialAccount.id == uuid.UUID(str(req.account_id)),
                    SocialAccount.user_id == current_user.id,
                )
            )
            account = account_result.scalar_one_or_none()
            if account:
                platform_result = await _send_unified_reply(
                    account,
                    {
                        "message": reply,
                        "recipient_id": req.recipient_id,
                        "reply_mode": req.reply_mode or ("dm" if item_type == "dm" else "comment"),
                        "reply_target_id": req.reply_target_id or req.message_id,
                        "reply_parent_id": req.reply_parent_id,
                        "conversation_id": req.message_id,
                    },
                )
                delivery_status = str(platform_result.get("status") or "sent")
            else:
                delivery_status = "account_not_found"
        except Exception as exc:
            logger.warning("RAG auto-reply delivery skipped: %s", exc)
            delivery_status = "delivery_failed"

    requires_team_review = (
        requires_human
        or delivery_status in {"delivery_failed", "account_not_found"}
        or _reply_requires_team_review(reply)
    )
    if req.account_id and requires_team_review:
        title, description = _human_review_alert_text(
            item_type=item_type,
            platform=req.platform,
            message=req.content,
            reply=reply,
            confidence=max_relevance,
            threshold=float(req.confidence_threshold),
        )
        target_key = (
            f"rag:{item_type}:{req.platform}:{req.reply_parent_id or ''}:{req.message_id}"
            if item_type == "comment"
            else f"rag:{item_type}:{req.platform}:{req.recipient_id or req.message_id}"
        )
        action_url = (
            f"/inbox?tab=posts&post={req.reply_parent_id or ''}&comment={req.reply_target_id or req.message_id}"
            if item_type == "comment"
            else f"/inbox?tab=messages&dm={req.message_id}"
        )
        await ensure_activity_alert(
            db,
            account_id=req.account_id,
            severity=AlertSeverity.HIGH if delivery_status == "delivery_failed" else AlertSeverity.MEDIUM,
            alert_type="rag_human_review",
            title=title,
            description=description,
            metadata={
                "target_kind": item_type,
                "target_key": target_key,
                "account_id": str(req.account_id),
                "platform": req.platform,
                "message_id": req.message_id,
                "reply_target_id": req.reply_target_id,
                "reply_parent_id": req.reply_parent_id,
                "recipient_id": req.recipient_id,
                "confidence": round(max_relevance, 4),
                "confidence_threshold": req.confidence_threshold,
                "delivery_status": delivery_status,
                "requires_human": requires_human,
                "client_message": req.content[:500],
                "ai_reply": reply[:500],
                "action_url": action_url,
            },
        )

    return {
        "reply": reply,
        "message_id": req.message_id,
        "platform": req.platform,
        "type": item_type,
        "language": language,
        "detected_language": detected_language,
        "confidence": round(max_relevance, 4),
        "confidence_threshold": req.confidence_threshold,
        "requires_human": requires_human,
        "requires_team_review": requires_team_review,
        "delivery_status": delivery_status,
        "platform_result": platform_result,
    }


@router.post("/rag/ingest-text")
async def ingest_text(
    req: RAGTextRequest,
    current_user: User = Depends(get_current_user),
):
    """Ingere un texte brut dans la base de connaissances RAG."""
    chunks = get_rag_service().ingest_text(req.text, source=req.name)
    return {"status": "ingested", "source": req.name, "chunks": chunks}


@router.post("/rag/ingest")
async def ingest_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Ingere un fichier dans la base de connaissances RAG."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file.filename}") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        chunks = get_rag_service().ingest_file(tmp_path)
    finally:
        os.unlink(tmp_path)

    return {"status": "ingested", "filename": file.filename, "chunks": chunks}


@router.get("/rag/sources")
async def list_rag_sources(current_user: User = Depends(get_current_user)):
    """Liste les fichiers ingeres dans la base RAG."""
    return {"sources": get_rag_service().list_sources()}


@router.delete("/rag/sources/{source}")
async def delete_rag_source(source: str, current_user: User = Depends(get_current_user)):
    """Supprime une source de la base RAG."""
    get_rag_service().delete_source(source)
    return {"status": "deleted", "source": source}
