"""DM chatbot router."""
from __future__ import annotations

from datetime import datetime, timezone
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth_utils import get_current_user
from api.routes.posts import _fetch_live_comments_for_account, _fetch_live_posts_for_account
from core.config import get_settings
from core.database import get_db
from models.domain import Platform, SocialAccount, User
from services.facebook_graph import FacebookGraphService
from services.instagram_graph import InstagramService
from services.linkedIn_graph import LinkedInGraphService
from services.threads_graph import ThreadsGraphService
from services.nlp_pipeline import nlp_pipeline
from services.rag_service import get_rag_service
from services.llm_orchestrator import LLMRequest, get_llm_orchestrator
from services.social_activity_store import ensure_negative_dm_alert, persist_live_dm_item
from services.social_account_tokens import resolve_account_access_token, resolve_account_access_tokens
from services.twitter_graph import TwitterGraphService

from models.domain import Platform, SocialAccount, User, DirectMessage

router = APIRouter()
settings = get_settings()


def _detect_language(text: str) -> str:
    if any("\u0600" <= ch <= "\u06FF" for ch in text):
        return "ar"
    lowered = text.lower()
    if any(token in lowered for token in ("bonjour", "merci", "prix", "commande", "livraison")):
        return "fr"
    return "en"


def _detect_intent(text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ("bonjour", "salut", "hello", "hi", "السلام", "مرحبا")):
        return "greeting"
    if any(token in lowered for token in ("prix", "price", "combien", "tarif", "بشحال")):
        return "price_request"
    if any(token in lowered for token in ("probleme", "problème", "problem", "complaint", "commande", "refund", "remboursement")):
        return "complaint"
    return "general"


def _fallback_dm_message(language: str) -> str:
    if language == "ar":
        return "شكرا لرسالتك. سنرد عليك في أقرب وقت ممكن."
    if language == "fr":
        return "Merci pour votre message. Nous revenons vers vous très vite."
    return "Thank you for your message. We will get back to you shortly."


def _message_text(payload: dict) -> str:
    text = (payload.get("text") or payload.get("message") or "").strip()
    if text:
        return text
    attachments = payload.get("attachments") or {}
    data = attachments.get("data") if isinstance(attachments, dict) else None
    if data:
        return "[Attachment]"
    return ""


def _edge_items(payload: dict | list | None) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
    return []


def _parse_meta_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _is_recent_enough_for_messenger(value: str | None) -> bool:
    timestamp = _parse_meta_timestamp(value)
    if not timestamp:
        return True
    delta = datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)
    return delta.total_seconds() <= 24 * 60 * 60


def _is_messenger_window_expired_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "(#10)" in text and ("délai autorisé" in text or "delai autorise" in text or "outside" in text)


def _messenger_window_expired_detail() -> str:
    return (
        "Impossible d'envoyer ce DM: la fenetre Messenger de 24h est expiree. "
        "Le client doit renvoyer un message a la Page, ou il faut utiliser un Message Tag Meta autorise "
        "pour un cas non promotionnel."
    )


def _normalize_conversation_messages(account: SocialAccount, raw_messages: list[dict]) -> list[dict]:
    normalized: list[dict] = []
    for raw in sorted(raw_messages, key=lambda item: item.get("created_time") or item.get("timestamp") or ""):
        sender = raw.get("from") or {}
        sender_id = str(sender.get("id") or "").strip()
        text = _message_text(raw)
        if not text:
            continue
        is_from_page = bool(sender_id and sender_id == str(account.account_id))
        normalized.append({
            "id": str(raw.get("id") or f"{account.id}:{raw.get('created_time') or len(normalized)}"),
            "text": text,
            "timestamp": raw.get("created_time") or raw.get("timestamp"),
            "author": sender.get("name") or sender.get("username") or (account.account_name if is_from_page else "Client"),
            "sender_id": sender_id,
            "is_from_page": is_from_page,
        })
    return normalized


@router.post("/respond")
async def dm_respond(
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate AI chatbot response for a DM (multilingual FR/AR/EN)."""
    message = payload.get("message", "")
    language = payload.get("language") or _detect_language(message)
    intent = _detect_intent(message)
    requires_human = intent == "complaint"

    llm_enabled = bool(settings.anthropic_api_key or settings.hugging_face_api)
    if not llm_enabled:
        response_text = _fallback_dm_message(language)
    else:
        response_text = await get_rag_service().chat_with_rag(
            user_message=message,
            conversation_history=payload.get("history", []),
            system_context=payload.get("brand_knowledge", ""),
            db=db,
            user_id=str(current_user.id),
            session_id=f"dm:{current_user.id}:{payload.get('conversation_id') or payload.get('sender_id') or 'general'}",
        )

    return {
        "message": response_text,
        "language": language,
        "intent": intent,
        "confidence": 0.78 if llm_enabled else 0.45,
        "requires_human": requires_human,
        "suggested_actions": ["escalate_to_human"] if requires_human else ["reply"],
    }


@router.post("/analyze")
async def analyze_dm_message(
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Analyze a DM through the local NLP model and generate a Claude reply suggestion via the central graph."""
    text = str(payload.get("message") or payload.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "message is required")

    analysis = await nlp_pipeline.process(text)
    label = "spam" if analysis.is_spam else "toxic" if analysis.is_toxic else analysis.sentiment
    language = payload.get("language") or _detect_language(text)
    suggested_reply = _fallback_dm_message(language)

    if settings.anthropic_api_key or settings.hugging_face_api:
        system_prompt = (
            "Tu es l'assistant social media de la marque. "
            "Genere une reponse courte, professionnelle, humaine et utile. "
            "Si la demande est sensible, propose de transmettre au service client. "
            "Reponds seulement avec le texte de la reponse, sans JSON."
        )
        try:
            response = await get_llm_orchestrator().generate_text(
                LLMRequest(
                    user_message=f"Message client: {text}",
                    system_prompt=system_prompt,
                    user_id=str(current_user.id),
                    session_id=f"dm-analysis:{current_user.id}:{payload.get('conversation_id') or payload.get('sender_id') or 'manual'}",
                    feature="dm_analysis",
                    persist_memory=True,
                    metadata={"label": label, "language": language},
                    max_tokens=300,
                ),
                db=db,
            )
            suggested_reply = response.text or suggested_reply
        except Exception as exc:
            logger.warning("DM reply suggestion skipped: {}", exc)

    return {
        "sentiment": label,
        "sentimentScore": analysis.sentiment_score,
        "emotion": "neutre",
        "isQuestion": "?" in text,
        "isLead": any(token in text.lower() for token in ("prix", "price", "tarif", "commande", "devis", "buy", "acheter")),
        "isToxic": analysis.is_toxic,
        "isSpam": analysis.is_spam,
        "suggestedReply": suggested_reply,
        "analyzed": True,
    }


def _normalize_instagram_conversation(account: SocialAccount, conversation: dict) -> dict | None:
    messages = _edge_items(conversation.get("messages"))
    participants = _edge_items(conversation.get("participants"))
    if messages:
        messages = sorted(messages, key=lambda item: item.get("created_time") or "", reverse=True)
        latest = messages[0]
        sender = latest.get("from") or {}
        timestamp = latest.get("created_time") or conversation.get("updated_time")
    else:
        latest = {}
        sender = next((p for p in participants if p.get("id") != account.account_id), participants[0] if participants else {})
        timestamp = conversation.get("updated_time")

    message = _message_text(latest) or _message_text(conversation) or str(conversation.get("snippet") or "").strip()
    if not message:
        message = "[Message unavailable from API]"

    recipient_id = sender.get("id") or ""
    can_reply = bool(recipient_id)
    return {
        "id": conversation.get("id") or latest.get("id") or f"{account.id}:{timestamp}",
        "account_id": str(account.id),
        "platform": account.platform.value,
        "account_name": account.account_name,
        "source_type": "dm",
        "conversation_id": conversation.get("id"),
        "sender_id": recipient_id,
        "sender_name": sender.get("username") or sender.get("name") or "Instagram user",
        "message": message,
        "messages": _normalize_conversation_messages(account, messages),
        "timestamp": timestamp,
        "recipient_id": recipient_id,
        "can_reply": can_reply,
        "reply_disabled_reason": "" if can_reply else "Identifiant destinataire Instagram introuvable.",
        "reply_mode": "dm",
        "reply_target_id": recipient_id,
        "reply_action_label": "Repondre en DM",
    }


async def _fetch_instagram_conversations(account: SocialAccount) -> list[dict]:
    instagram_account_id = str(account.account_id or "").strip()
    metadata = account.metadata_ or {}
    page_id = str(metadata.get("facebook_page_id") or "").strip()
    token_candidates = resolve_account_access_tokens(account)
    last_error: Exception | None = None

    logger.info(
        "Instagram DM fetch start account_name='{}' account_id='{}' facebook_page_id='{}' token_sources={}",
        account.account_name,
        instagram_account_id,
        page_id,
        [source for _token, source in token_candidates],
    )

    if not token_candidates:
        raise ValueError(f"No access token available for Instagram account '{account.account_name}'")

    for token, token_source in token_candidates:
        svc = InstagramService(token)
        try:
            if not instagram_account_id:
                continue
            try:
                target_id = page_id if page_id else instagram_account_id
                #target_id = 1183477331505585
                conversations = await svc.get_conversations(target_id)
                logger.info(
                    "Instagram DM fetch token_source='{}' returned {} conversation(s) for account_name='{}'",
                    token_source,
                    len(conversations),
                    account.account_name,
                )
                return conversations
            except Exception as exc:
                last_error = exc
                logger.warning("Instagram DM fetch failed for '{}': {}", account.account_name, exc)
        finally:
            await svc.close()

    if not instagram_account_id:
        raise ValueError(f"Instagram account_id missing for account '{account.account_name}'")
    if last_error:
        raise ValueError(f"{last_error} | diagnostics: instagram_account_id={instagram_account_id}, facebook_page_id={page_id}")
    return []


def _normalize_facebook_conversation(account: SocialAccount, conversation: dict) -> dict:
    participants = ((conversation.get("participants") or {}).get("data") or [])
    messages = _edge_items(conversation.get("messages"))
    other = next((p for p in participants if p.get("id") != account.account_id), participants[0] if participants else {})
    recipient_id = other.get("id") or ""
    is_window_open = _is_recent_enough_for_messenger(conversation.get("updated_time"))
    can_reply = bool(recipient_id) and is_window_open
    return {
        "id": conversation.get("id"),
        "account_id": str(account.id),
        "platform": account.platform.value,
        "account_name": account.account_name,
        "source_type": "dm",
        "conversation_id": conversation.get("id"),
        "sender_id": recipient_id,
        "sender_name": other.get("name") or "Facebook user",
        "message": _message_text(conversation) or conversation.get("snippet") or "",
        "messages": _normalize_conversation_messages(account, messages),
        "timestamp": conversation.get("updated_time"),
        "recipient_id": recipient_id,
        "can_reply": can_reply,
        "reply_disabled_reason": (
            ""
            if can_reply
            else (
                "La fenetre Messenger de 24h est expiree. Demandez au client de renvoyer un message avant de repondre."
                if recipient_id
                else "Identifiant destinataire Facebook introuvable."
            )
        ),
        "reply_mode": "dm",
        "reply_target_id": recipient_id,
        "reply_action_label": "Repondre sur Facebook",
    }


async def _build_social_fallback_items(account: SocialAccount, limit: int = 5) -> list[dict]:
    items: list[dict] = []
    live_posts = await _fetch_live_posts_for_account(account, limit=max(limit, 3))

    for post in live_posts[:limit]:
        platform_post_id = str(post.get("id") or "").strip()
        if not platform_post_id:
            continue
        try:
            comments = await _fetch_live_comments_for_account(account, platform_post_id)
        except Exception:
            comments = []

        for comment in comments[:2]:
            can_reply = account.platform in {Platform.INSTAGRAM, Platform.FACEBOOK, Platform.LINKEDIN}
            items.append({
                "id": f"{account.id}:{platform_post_id}:{comment.get('id')}",
                "account_id": str(account.id),
                "platform": account.platform.value,
                "account_name": account.account_name,
                "conversation_id": platform_post_id,
                "sender_id": str(comment.get("id") or ""),
                "sender_name": comment.get("author") or f"{account.platform.value.title()} user",
                "message": comment.get("text") or "[Comment unavailable]",
                "timestamp": comment.get("timestamp") or post.get("timestamp"),
                "recipient_id": "",
                "source_type": "comment",
                "can_reply": can_reply,
                "reply_disabled_reason": "" if can_reply else "La reponse n'est pas disponible pour cette plateforme.",
                "reply_mode": "comment",
                "reply_target_id": str(comment.get("id") or ""),
                "reply_parent_id": platform_post_id,
                "reply_action_label": "Repondre au commentaire",
            })

    if items:
        return items[:limit]

    return [{
        "id": f"{account.id}:{post.get('id')}",
        "account_id": str(account.id),
        "platform": account.platform.value,
        "account_name": account.account_name,
        "conversation_id": str(post.get("id") or ""),
        "sender_id": "",
        "sender_name": account.account_name,
        "message": post.get("text") or f"Aucune conversation disponible pour {account.platform.value}.",
        "timestamp": post.get("timestamp"),
        "recipient_id": "",
        "source_type": "post",
        "can_reply": account.platform in {Platform.LINKEDIN, Platform.TWITTER},
        "reply_disabled_reason": "" if account.platform in {Platform.LINKEDIN, Platform.TWITTER} else "La reponse n'est pas disponible pour cette plateforme.",
        "reply_mode": "post_reply",
        "reply_target_id": str(post.get("id") or ""),
        "reply_parent_id": str(post.get("id") or ""),
        "reply_action_label": "Publier une reponse",
    } for post in live_posts[:limit]]


def _matches_inbox_kind(item: dict, kind: str) -> bool:
    source_type = str(item.get("source_type") or "dm").lower()
    if kind == "dm":
        return source_type == "dm"
    if kind == "interactions":
        return source_type != "dm"
    return True


async def _send_unified_reply(account: SocialAccount, payload: dict) -> dict:
    message = str(payload.get("message") or "").strip()
    reply_mode = str(payload.get("reply_mode") or "").strip().lower()
    reply_target_id = str(payload.get("reply_target_id") or payload.get("recipient_id") or "").strip()
    reply_parent_id = str(payload.get("reply_parent_id") or payload.get("conversation_id") or "").strip()

    if not message:
        raise HTTPException(400, "message is required")

    if account.platform == Platform.INSTAGRAM:
        token, _token_source = resolve_account_access_token(account)
        svc = InstagramService(token)
        try:
            if reply_mode == "comment":
                if not reply_target_id:
                    raise HTTPException(400, "reply_target_id is required for Instagram comment replies")
                response = await svc.reply_to_comment(reply_target_id, message)
                return {"status": "sent", "mode": "comment", "result": response}

            if not reply_target_id:
                raise HTTPException(400, "recipient_id is required for Instagram DM replies")
                        # Use the Facebook Page ID instead of the Instagram Account ID
            metadata = account.metadata_ or {}
            page_id = str(metadata.get("facebook_page_id") or account.account_id).strip()
            response = await svc.send_dm(page_id, reply_target_id, message)
            return {"status": "sent", "mode": "dm", "result": response}
        finally:
            await svc.close()

    if account.platform == Platform.FACEBOOK:
        svc = FacebookGraphService(account.access_token)
        try:
            if reply_mode == "comment":
                target_id = reply_target_id or reply_parent_id
                if not target_id:
                    raise HTTPException(400, "reply_target_id is required for Facebook comment replies")
                response = await svc.add_comment(target_id, message)
                return {"status": "sent", "mode": "comment", "result": response}

            if not reply_target_id:
                raise HTTPException(400, "recipient_id is required for Facebook DM replies")
            response = await svc.send_page_message(account.account_id, reply_target_id, message)
            return {"status": "sent", "mode": "dm", "result": response}
        finally:
            await svc.close()

    if account.platform == Platform.LINKEDIN:
        if reply_mode not in {"comment", "post_reply"}:
            raise HTTPException(400, "LinkedIn replies are currently supported only as post comments")
        target_urn = reply_parent_id or reply_target_id
        if not target_urn:
            raise HTTPException(400, "reply_parent_id is required for LinkedIn replies")
        svc = LinkedInGraphService(account.access_token)
        try:
            response = await svc.add_comment(post_urn=target_urn, actor_urn=account.account_id, text=message)
            return {"status": "sent", "mode": "comment", "result": response}
        finally:
            await svc.close()

    if account.platform == Platform.TWITTER:
        if reply_mode != "post_reply":
            raise HTTPException(400, "Twitter replies are currently supported only as replies to posts")
        target_id = reply_target_id or reply_parent_id
        if not target_id:
            raise HTTPException(400, "reply_target_id is required for Twitter replies")
        svc = TwitterGraphService(account.access_token)
        try:
            response = await svc.create_reply_tweet(target_id, message)
            return {"status": "sent", "mode": "post_reply", "result": response}
        finally:
            await svc.close()

    if account.platform == Platform.THREADS:
        if reply_mode != "comment":
            raise HTTPException(400, "Threads replies are currently supported only as comments")
        target_id = reply_target_id or reply_parent_id
        if not target_id:
            raise HTTPException(400, "reply_target_id is required for Threads replies")
        svc = ThreadsGraphService(account.access_token)
        try:
            response = await svc.reply_to_comment(account.account_id, target_id, message)
            return {"status": "sent", "mode": "comment", "result": response}
        finally:
            await svc.close()

    if account.platform == Platform.YOUTUBE:
        if reply_mode != "comment":
            raise HTTPException(400, "YouTube replies are currently supported only as comments")
        target_id = reply_target_id or reply_parent_id
        if not target_id:
            raise HTTPException(400, "reply_target_id is required for YouTube comment replies")
        from services.youtube_graph import YouTubeGraphService
        svc = YouTubeGraphService(account.access_token)
        try:
            response = await svc.reply_to_comment(target_id, message)
            return {"status": "sent", "mode": "comment", "result": response}
        finally:
            await svc.close()

    raise HTTPException(400, f"Reply is not yet supported for {account.platform.value} accounts in this integration.")


@router.get("/live")
async def get_live_inbox(
    account_id: str | None = Query(default=None),
    kind: str = Query(default="all", pattern="^(all|dm|interactions)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(SocialAccount).where(SocialAccount.user_id == current_user.id)
    if account_id:
        query = query.where(SocialAccount.id == uuid.UUID(account_id))

    result = await db.execute(query)
    accounts = result.scalars().all()
    items: list[dict] = []
    errors: list[dict] = []

    for account in accounts:
        try:
            if account.platform == Platform.INSTAGRAM:
                conversations = await _fetch_instagram_conversations(account)
                for conversation in conversations:
                    normalized = _normalize_instagram_conversation(account, conversation)
                    if normalized:
                        items.append(normalized)
                continue

            if account.platform == Platform.FACEBOOK:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(
                        f"https://graph.facebook.com/v20.0/{account.account_id}/conversations",
                        params={
                            "access_token": account.access_token,
                            "fields": "id,snippet,updated_time,message_count,unread_count,participants,messages.limit(100){id,message,from,to,created_time,attachments}",
                        },
                    )
                data = resp.json()
                if "error" in data:
                    raise HTTPException(400, f"Facebook API error: {data['error']['message']}")
                items.extend(_normalize_facebook_conversation(account, c) for c in data.get("data", []))
                continue

            if kind != "dm":
                items.extend(await _build_social_fallback_items(account))
        except Exception as exc:
            errors.append({
                "account_id": str(account.id),
                "platform": account.platform.value,
                "account_name": account.account_name,
                "error": str(exc),
            })

    items = [item for item in items if _matches_inbox_kind(item, kind)]

    for item in items:
        if item.get("message"):
            item["label"] = "pending"
            item["sentiment_score"] = 0.0
            item["is_spam"] = False
            item["is_toxic"] = False
            item["is_question"] = "?" in item["message"]
            item["is_lead"] = any(token in item["message"].lower() for token in ("prix", "price", "tarif", "commande", "devis", "buy", "acheter"))
        for message in item.get("messages") or []:
            if message.get("is_from_page") or not message.get("text"):
                continue
            message["label"] = "pending"
            message["sentiment_score"] = 0.0
            message["is_spam"] = False
            message["is_toxic"] = False
            message["is_question"] = "?" in message["text"]
            message["is_lead"] = any(token in message["text"].lower() for token in ("prix", "price", "tarif", "commande", "devis", "buy", "acheter"))

        try:
            stored = await persist_live_dm_item(db, item)
            item["stored_dm_id"] = str(stored.id)
            
            # --- ADD THIS TO SYNC WITH DATABASE ---
            if stored.intent and stored.intent != "pending":
                item["label"] = stored.intent
                item["is_toxic"] = stored.intent == "toxic"
                item["is_spam"] = stored.intent == "spam"
                item["sentiment_score"] = stored.sentiment_score

                        # --- SYNC OLDER MESSAGES FROM DATABASE ---
            past_dms_result = await db.execute(
                select(DirectMessage.message, DirectMessage.intent)
                .where(
                    DirectMessage.account_id == item["account_id"],
                    DirectMessage.intent != "pending"
                )
            )
            # Make it 100% case-insensitive to guarantee it catches "Arnaque !"
            intent_map = {str(row[0]).strip().lower(): str(row[1]) for row in past_dms_result.all() if row[0] and row[1]}
            
            for msg in item.get("messages") or []:
                msg_text = str(msg.get("text") or "").strip().lower()
                if msg_text and msg_text in intent_map:
                    msg["label"] = intent_map[msg_text]
                    msg["is_toxic"] = intent_map[msg_text] == "toxic"
                    msg["is_spam"] = intent_map[msg_text] == "spam"
                else:
                    # If the message was never analyzed (not in DB), don't show 'pending'
                    if msg.get("label") == "pending":
                        msg["label"] = "neutral"
                
            if item.get("label") in {"negative", "toxic"} or item.get("is_toxic"):
                await ensure_negative_dm_alert(db, item=item)
        except Exception as exc:
            logger.warning("DM persistence skipped for '{}': {}", item.get("id"), exc)

    items.sort(key=lambda item: item.get("timestamp") or "", reverse=True)
    return {"items": items, "errors": errors}


@router.post("/send")
async def send_live_dm(
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    account_id = payload.get("account_id")
    message = (payload.get("message") or "").strip()
    if not account_id or not message:
        raise HTTPException(400, "account_id and message are required")

    result = await db.execute(
        select(SocialAccount).where(
            SocialAccount.id == uuid.UUID(str(account_id)),
            SocialAccount.user_id == current_user.id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(404, "Account not found")

    try:
        response = await _send_unified_reply(account, payload)
    except HTTPException:
        raise
    except ValueError as exc:
        if _is_messenger_window_expired_error(exc):
            raise HTTPException(status_code=403, detail=_messenger_window_expired_detail()) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result = response.get("result")
    if isinstance(result, dict) and result.get("error"):
        raise HTTPException(400, str(result["error"]))
    return response
