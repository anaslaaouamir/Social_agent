"""
Unified NLP pipeline for spam, toxicity, sentiment, and lightweight topicing.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
import asyncio
import threading
import json

logger = logging.getLogger(__name__)

MODEL_DIR = Path("./data/models")
SENTIMENT_MODEL_DIR = MODEL_DIR / "mbert_sentiment_finetuned"
TOXIC_MODEL_DIR = MODEL_DIR / "mbert_toxic_finetuned"

HF_SENTIMENT_REVIEW_MODELS = [
    "google/flan-t5-small",
    "google/flan-t5-base",
]

def _resolve_model_path(model_dir: Path, fallback_model: str) -> str:
    if not model_dir.exists():
        return fallback_model

    if (model_dir / "config.json").exists():
        return str(model_dir)

    checkpoints = sorted(
        [path for path in model_dir.glob("checkpoint-*") if (path / "config.json").exists()],
        key=lambda path: path.stat().st_mtime,
    )
    if checkpoints:
        resolved = checkpoints[-1]
        logger.info("Using checkpoint model from %s", resolved)
        return str(resolved)

    return fallback_model

def _clean_text(text: str) -> str:
    """Normalize noisy social text before model inference."""
    text = re.sub(r"(.)\1{3,}", r"\1\1", text)
    return text.strip()

def _looks_like_request_or_requirement(text: str) -> bool:
    lowered = text.lower()
    request_patterns = [
        r"\bje\s+(veux|voudrais|cherche|souhaite|besoin)\b",
        r"\bon\s+(veut|voudrait|cherche|souhaite|besoin)\b",
        r"\bnous\s+(voulons|voudrions|cherchons|souhaitons|avons besoin)\b",
        r"\bi\s+(want|need|am looking for|would like)\b",
        r"\bwe\s+(want|need|are looking for|would like)\b",
        r"\bcan you\b",
        r"\bpouvez[- ]vous\b",
        r"\best[- ]ce que\b",
        r"\b(comment|combien|quoi|quel|quelle|quels|quelles|ou|où|quand)\b",
        r"\b(prix|tarif|tarifs|devis|contact|contacter|contactez|joindre|appelez|whatsapp)\b",
        r"\b(processus|procedure|procédure|methode|méthode|travail|travailler|agents?)\b",
        r"\bwach\b",
        r"\bbghit\b",
        r"\bkhasni\b",
        r"\bchhal\b",
        r"\btaman\b",
        r"\bprix\b",
    ]
    return any(re.search(pattern, lowered) for pattern in request_patterns)

def _has_explicit_negative_feedback(text: str) -> bool:
    lowered = text.lower()
    negative_patterns = [
        r"\b(nul|arnaque|mauvais|horrible|catastroph|decu|deçu|insatisfait|plainte|probleme|problème)\b",
        r"\b(pas aime|pas aimé|gaspille|gaspillé|perdu mon temps|gaspille mon temps|gaspillé mon temps)\b",
        r"\b(remboursement|refund|scam|bad|terrible|awful|worst|complaint|angry|not happy)\b",
        r"\b(khayb|khayba|machi mzyan|mashi mzyan|mazyanch|kharay|nصب|نصب|سيء|سيئة)\b",
    ]
    return any(re.search(pattern, lowered) for pattern in negative_patterns)

def _adjust_sentiment_for_business_context(label: str, score: float, text: str) -> tuple[str, float]:
    if label != "negative":
        return label, score
    if _looks_like_request_or_requirement(text) and not _has_explicit_negative_feedback(text):
        return "neutral", 0.0
    return label, score

def _parse_llm_sentiment_label(raw: str) -> str | None:
    cleaned = str(raw or "").strip()
    if not cleaned:
        return None
    try:
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`").replace("json", "", 1).strip()
        data = json.loads(cleaned)
        label = str(data.get("label") or "").lower().strip()
    except Exception:
        match = re.search(r"\b(negative|neutral)\b", cleaned.lower())
        label = match.group(1) if match else ""
    return label if label in {"negative", "neutral"} else None

@dataclass
class NLPResult:
    text: str
    is_spam: bool
    spam_score: float
    is_toxic: bool
    toxic_score: float
    sentiment: str
    sentiment_score: float
    topic_id: int
    topic_label: str
    topic_keywords: list[str]
    language: str


class NLPPipeline:
    def __init__(self):
        self._sentiment_model = None
        self._toxic_model = None
        self._topic_model = None

        self._sentiment_lock = threading.Lock()
        self._toxic_lock = threading.Lock()
        self._topic_lock = threading.Lock()

        self._toxic_model_failed = False
        self._toxic_error_logged = False
        self._sentiment_llm_review_disabled = False
        self._sentiment_llm_review_error_logged = False
        
        self._spam_keywords = self._load_spam_keywords()
        self._toxic_keywords = self._load_toxic_keywords()
        self._topic_fitted = False

    def _get_sentiment_model(self):
        if self._sentiment_model is None:
            with self._sentiment_lock:
                if self._sentiment_model is None:
                    from transformers import pipeline as hf_pipeline

                    model_name = _resolve_model_path(
                        SENTIMENT_MODEL_DIR,
                        "nlptown/bert-base-multilingual-uncased-sentiment",
                    )
                    self._sentiment_model = hf_pipeline(
                        "text-classification",
                        model=model_name,
                        top_k=None,
                        truncation=True,
                        max_length=512,
                    )
        return self._sentiment_model

    def _get_toxic_model(self):
        if self._toxic_model is None and not self._toxic_model_failed:
            with self._toxic_lock:
                if self._toxic_model is None:
                    try:
                        from transformers import (
                            AutoModelForSequenceClassification,
                            AutoTokenizer,
                            pipeline as hf_pipeline,
                        )

                        model_name = _resolve_model_path(
                            TOXIC_MODEL_DIR,
                            "unitary/multilingual-toxic-xlm-roberta",
                        )
                        tokenizer = AutoTokenizer.from_pretrained(
                            model_name,
                            use_fast=False,
                        )
                        model = AutoModelForSequenceClassification.from_pretrained(
                            model_name
                        )
                        self._toxic_model = hf_pipeline(
                            "text-classification",
                            model=model,
                            tokenizer=tokenizer,
                            top_k=None,
                            truncation=True,
                            max_length=512,
                        )
                    except Exception as exc:
                        self._toxic_model_failed = True
                        if not self._toxic_error_logged:
                            logger.warning("Toxic model unavailable, using heuristic fallback: %s", exc)
                            self._toxic_error_logged = True
        return self._toxic_model

    def _get_bertopic_model(self):
        if self._topic_model is None:
            with self._topic_lock:
                if self._topic_model is None:
                    from bertopic import BERTopic
                    from sentence_transformers import SentenceTransformer

                    embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
                    self._topic_model = BERTopic(
                        embedding_model=embedding_model,
                        language="multilingual",
                        calculate_probabilities=True,
                        verbose=False,
                        min_topic_size=5,
                    )
        return self._topic_model

    def _load_spam_keywords(self) -> set[str]:
        return {
            "follow4follow", "f4f", "like4like", "l4l", "dm for promo",
            "check my bio", "link in bio", "buy followers", "gain followers",
            "onlyfans", "click here", "free money", "win prize", "giveaway",
            "crypto", "btc", "forex", "investment", "telegram", "whatsapp me",
            "inbox me", "urgent", "limited offer", "promo code", "contact me",
        }

    def _load_toxic_keywords(self) -> dict[str, float]:
        return {
            "idiot": 0.35, "stupid": 0.35, "dumb": 0.35, "moron": 0.4,
            "loser": 0.35, "trash": 0.25, "garbage": 0.25, "hate you": 0.45,
            "i hate": 0.25, "shut up": 0.35, "fuck": 0.6, "fucking": 0.6,
            "bitch": 0.6, "asshole": 0.6, "bastard": 0.5, "bullshit": 0.45,
            "arnaque": 0.25, "nul": 0.2, "horrible service": 0.25,
            "kill you": 0.85, "go die": 0.85, "hate speech": 0.85,
        }

    def detect_spam(self, text: str) -> tuple[bool, float]:
        text_lower = text.lower()
        url_count = len(re.findall(r"http[s]?://", text_lower))
        emoji_spam = len(re.findall(r"[\U0001F600-\U0001F64F]", text)) > 8
        keyword_hit = any(kw in text_lower for kw in self._spam_keywords)
        repeat_chars = bool(re.search(r"(.)\1{4,}", text_lower))
        repeated_punct = len(re.findall(r"[!?$]{3,}", text)) > 0
        uppercase_ratio = (
            sum(1 for ch in text if ch.isupper()) / max(sum(1 for ch in text if ch.isalpha()), 1)
        )

        score = 0.0
        if url_count >= 2: score += 0.4
        if url_count == 1: score += 0.15
        if emoji_spam: score += 0.2
        if keyword_hit: score += 0.5
        if repeat_chars: score += 0.1
        if repeated_punct: score += 0.15
        if uppercase_ratio > 0.7 and len(text) > 12: score += 0.15
        if len(text) < 5: score += 0.1

        score = min(score, 1.0)
        return score >= 0.5, score

    def _detect_toxic_heuristic(self, text: str) -> tuple[bool, float]:
        lowered = text.lower()
        score = 0.0
        for keyword, weight in self._toxic_keywords.items():
            if keyword in lowered:
                score += weight
        if re.search(r"\b(hate|idiot|stupid|dumb|moron)\b.*\b(you|u|people|person)\b", lowered):
            score += 0.2
        if re.search(r"\b(fuck|bitch|asshole|bastard)\b", lowered):
            score += 0.2
        if re.search(r"[!?]{3,}", text):
            score += 0.05
        score = min(score, 0.99)
        return score > 0.45, score

    def detect_toxic(self, text: str) -> tuple[bool, float]:
        model = self._get_toxic_model()
        if model is None:
            return self._detect_toxic_heuristic(text)

        try:
            results = model(_clean_text(text[:512]))[0]
            if isinstance(results, dict):
                results = [results]

            # Use both label formats for maximum stability
            toxic_score = next(
                (
                    item["score"]
                    for item in results
                    if "toxic" in str(item.get("label", "")).lower()
                    or "insult" in str(item.get("label", "")).lower()
                    or "obscene" in str(item.get("label", "")).lower()
                    or "threat" in str(item.get("label", "")).lower()
                    or str(item.get("label", "")).upper() == "LABEL_1"
                ),
                0.0,
            )

            # Combine AI score with robust heuristics so obvious toxic words aren't missed
            heuristic_is_toxic, heuristic_score = self._detect_toxic_heuristic(text)
            final_score = max(float(toxic_score), heuristic_score)

            return final_score > 0.45, final_score

        except Exception as exc:
            self._toxic_model = None
            self._toxic_model_failed = True
            if not self._toxic_error_logged:
                logger.warning("Toxic model inference failed, using heuristic fallback: %s", exc)
                self._toxic_error_logged = True
            return self._detect_toxic_heuristic(text)

    def analyze_sentiment(self, text: str) -> tuple[str, float]:
        try:
            model = self._get_sentiment_model()
            clean_txt = _clean_text(text[:512])
            results = model(clean_txt)[0]
            if isinstance(results, dict):
                results = [results]

            # Use current parsing format that avoids crashes
            direct_labels = {str(item.get("label", "")).lower() for item in results}
            if any(label in {"positive", "neutral", "negative"} for label in direct_labels):
                best = max(results, key=lambda item: float(item.get("score", 0.0)))
                label = str(best.get("label", "neutral")).lower()
                confidence = float(best.get("score", 0.0))
                sentiment_score = {
                    "positive": confidence,
                    "negative": -confidence,
                    "neutral": 0.0,
                }.get(label, 0.0)
            else:
                weighted_rating = 0.0
                total_confidence = 0.0
                for item in results:
                    match = re.search(r"([1-5])", str(item.get("label", "")))
                    if not match:
                        continue
                    stars = int(match.group(1))
                    confidence = float(item.get("score", 0.0))
                    weighted_rating += stars * confidence
                    total_confidence += confidence

                if total_confidence == 0.0:
                    label = "neutral"
                    sentiment_score = 0.0
                else:
                    avg_rating = weighted_rating / total_confidence
                    sentiment_score = max(-1.0, min(1.0, (avg_rating - 3.0) / 2.0))
                    if avg_rating >= 3.75:
                        label = "positive"
                    elif avg_rating <= 2.25:
                        label = "negative"
                    else:
                        label = "neutral"

            # Bring back the business context logic!
            label, sentiment_score = _adjust_sentiment_for_business_context(
                label,
                sentiment_score,
                clean_txt,
            )

            return label, round(sentiment_score, 4)
        except Exception as exc:
            logger.warning("Sentiment model error: %s", exc)
            return "neutral", 0.0

    async def verify_negative_sentiment_with_llm(self, text: str, score: float) -> tuple[str, float]:
        """Use a lightweight Hugging Face LLM as a second opinion for negative labels."""
        if self._sentiment_llm_review_disabled:
            return "negative", score
        try:
            from core.config import get_settings

            api_key = (get_settings().hugging_face_api or "").strip()
            if not api_key:
                return "negative", score

            prompt = f"""Classify this customer social media message as exactly one label: negative or neutral.

Rules:
- negative only if the customer expresses complaint, dissatisfaction, accusation, anger, rejection, wasted time, refund, scam, or a real problem.
- neutral if it is a question, information request, price, contact, process, quote, need, purchase intent, or a grammatical negation without complaint.

Message: {text[:700]}
Current mBERT label: negative, score {score}

Return JSON only: {{"label":"negative"}} or {{"label":"neutral"}}"""

            def _call(model_name: str) -> str:
                from huggingface_hub import InferenceClient
                client = InferenceClient(model=model_name, token=api_key)
                return str(
                    client.text_generation(
                        prompt,
                        max_new_tokens=48,
                        temperature=0.0,
                        return_full_text=False,
                    )
                )

            raw = ""
            last_error: Exception | None = None
            for model_name in HF_SENTIMENT_REVIEW_MODELS:
                try:
                    raw = await asyncio.to_thread(_call, model_name)
                    last_error = None
                    break
                except Exception as exc:
                    last_error = exc
                    logger.info("Sentiment review model unavailable %s: %s", model_name, exc)
            
            if last_error is not None:
                self._sentiment_llm_review_disabled = True
                if not self._sentiment_llm_review_error_logged:
                    logger.warning("Negative sentiment LLM verification disabled: %s", last_error)
                    self._sentiment_llm_review_error_logged = True
                return "negative", score

            llm_label = _parse_llm_sentiment_label(raw)
            if llm_label == "neutral":
                return "neutral", 0.0
            return "negative", score
        except Exception as exc:
            self._sentiment_llm_review_disabled = True
            if not self._sentiment_llm_review_error_logged:
                logger.warning("Negative sentiment LLM verification disabled: %s", exc)
                self._sentiment_llm_review_error_logged = True
            return "negative", score

    def get_unified_label(self, result: NLPResult) -> str:
        if result.is_spam: return "spam"
        if result.is_toxic: return "toxic"
        return result.sentiment

    def fit_topics(self, texts: list[str]) -> None:
        if len(texts) < 10:
            return
        model = self._get_bertopic_model()
        model.fit(texts)
        self._topic_fitted = True

    def get_topic(self, text: str) -> tuple[int, str, list[str]]:
        if not self._topic_fitted:
            return -1, "uncategorized", []
        try:
            model = self._get_bertopic_model()
            topics, _ = model.transform([text])
            topic_id = int(topics[0])
            topic_info = model.get_topic(topic_id)
            keywords = [word for word, _ in topic_info[:5]] if topic_info else []
            topic_label = "_".join(keywords[:3]) if keywords else "misc"
            return topic_id, topic_label, keywords
        except Exception as exc:
            logger.warning("BERTopic transform error: %s", exc)
            return -1, "error", []

    def get_topic_lda(self, text: str, lda_model=None, dictionary=None) -> tuple[int, list[str]]:
        if lda_model is None: return -1, []
        from gensim.utils import simple_preprocess
        bow = dictionary.doc2bow(simple_preprocess(text))
        topics = lda_model.get_document_topics(bow)
        if not topics: return -1, []
        best_topic = max(topics, key=lambda item: item[1])
        topic_id = best_topic[0]
        keywords = [word for word, _ in lda_model.show_topic(topic_id, topn=5)]
        return topic_id, keywords

    def detect_language(self, text: str) -> str:
        try:
            from langdetect import detect
            return detect(text)
        except Exception:
            return "unknown"

    async def process(self, text: str) -> NLPResult:
        text = _clean_text(text)
        if not text:
            return NLPResult(
                text=text,
                is_spam=False,
                spam_score=0.0,
                is_toxic=False,
                toxic_score=0.0,
                sentiment="neutral",
                sentiment_score=0.0,
                topic_id=-1,
                topic_label="empty",
                topic_keywords=[],
                language="unknown",
            )

        # Threading stability to prevent API hang
        is_spam, spam_score = await asyncio.to_thread(self.detect_spam, text)
        is_toxic, toxic_score = await asyncio.to_thread(self.detect_toxic, text)
        sentiment, sentiment_score = await asyncio.to_thread(self.analyze_sentiment, text)

        # Brought back the verification logic
        if sentiment == "negative":
            sentiment, sentiment_score = await self.verify_negative_sentiment_with_llm(
                text,
                sentiment_score,
            )

        topic_id, topic_label, topic_keywords = await asyncio.to_thread(self.get_topic, text)
        language = await asyncio.to_thread(self.detect_language, text)

        return NLPResult(
            text=text,
            is_spam=is_spam,
            spam_score=round(spam_score, 4),
            is_toxic=is_toxic,
            toxic_score=round(toxic_score, 4),
            sentiment=sentiment,
            sentiment_score=sentiment_score,
            topic_id=topic_id,
            topic_label=topic_label,
            topic_keywords=topic_keywords,
            language=language,
        )


nlp_pipeline = NLPPipeline()
