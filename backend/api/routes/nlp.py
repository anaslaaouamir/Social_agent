"""Routes NLP : analyse manuelle, feed unifie, entrainement engagement et RAG."""
from __future__ import annotations

import logging
import os
import tempfile

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth_utils import get_current_user
from core.database import get_db
from models.domain import Comment, Post, SentimentLabel, SocialAccount, User
from services.dataset_loader import build_engagement_training_df, load_instagram_dataset
from services.ml_engagement import engagement_predictor
from services.nlp_pipeline import nlp_pipeline
from services.rag_service import get_rag_service

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
        "predicted_reach": pred.predicted_reach,
        "confidence": pred.confidence,
        "best_timing": {"hour": pred.best_hour, "day": pred.best_day},
        "recommended_content_type": pred.recommended_content_type,
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
        train_df = build_engagement_training_df(
            instagram_df=ig_df,
            synthetic_size=payload.get("synthetic_size", 30_000),
        )
        metrics = engagement_predictor.train_on_dataset(train_df)
        logger.info("Training termine: %s", metrics)

    background_tasks.add_task(_train)
    return {"status": "training_started", "message": "Modele en cours d'entrainement"}


@router.post("/rag/chat")
async def rag_chat(req: RAGChatRequest, current_user: User = Depends(get_current_user)):
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
