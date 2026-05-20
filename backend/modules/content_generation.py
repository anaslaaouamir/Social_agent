"""
Module 2: Content Generation Engine
Generates platform-optimized captions, hashtags, and variants using Claude.
Supports FR/AR/EN with Moroccan cultural context.
"""
from __future__ import annotations
import json
import asyncio
import re
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from services.llm_orchestrator import LLMConfigurationError, LLMRequest, get_llm_orchestrator


class Platform(str, Enum):
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    LINKEDIN = "linkedin"
    FACEBOOK = "facebook"
    TWITTER = "twitter"
    THREADS = "threads"
    YOUTUBE = "youtube"
    PINTEREST = "pinterest"


class ToneOfVoice(str, Enum):
    BRAND = "brand"
    FUN = "fun"
    INFORMATIVE = "informative"
    PROMOTIONAL = "promotional"
    INSPIRATIONAL = "inspirational"


PLATFORM_CONSTRAINTS = {
    Platform.INSTAGRAM: {
        "max_chars": 2200,
        "style": "storytelling émotionnel, appel à l'action clair, emojis contextuels",
        "hashtag_limit": 30,
    },
    Platform.TIKTOK: {
        "max_chars": 150,
        "style": "accrocheur, court, tendance, voix de la génération Z",
        "hashtag_limit": 10,
    },
    Platform.LINKEDIN: {
        "max_chars": 3000,
        "style": "professionnel, informatif, insight business, pas d'emojis excessifs",
        "hashtag_limit": 5,
    },
    Platform.FACEBOOK: {
        "max_chars": 63206,
        "style": "conversationnel, questions engageantes, communauté",
        "hashtag_limit": 10,
    },
    Platform.TWITTER: {
        "max_chars": 280,
        "style": "concis, percutant, wit, thread si nécessaire",
        "hashtag_limit": 3,
    },
    Platform.THREADS: {
        "max_chars": 500,
        "style": "conversationnel, direct, communautaire, ton naturel",
        "hashtag_limit": 3,
    },
    Platform.YOUTUBE: {
        "max_chars": 5000,
        "style": "titre accrocheur, description claire, appel a l'abonnement et mots-cles video",
        "hashtag_limit": 15,
    },
    Platform.PINTEREST: {
        "max_chars": 500,
        "style": "descriptif, inspirationnel, mots-cles de decouverte et intention d'achat",
        "hashtag_limit": 20,
    },
}


@dataclass
class CaptionVariant:
    text: str
    platform: Platform
    tone: ToneOfVoice
    language: str
    char_count: int
    emojis: list[str]
    call_to_action: str
    predicted_engagement_score: float  # 0-100


@dataclass
class GeneratedContent:
    captions: list[CaptionVariant]
    hashtags: list[str]
    hashtag_categories: dict[str, list[str]]
    raw_hashtags_with_scores: list[dict]
    best_caption: CaptionVariant
    ab_test_pairs: list[tuple[CaptionVariant, CaptionVariant]]


class ContentGenerationEngine:
    """
    Content generation using Claude claude-sonnet-4-20250514.
    Generates 3-5 platform-optimized variants per post.
    Supports FR/AR/EN with Moroccan cultural adaptation.
    """

    MOROCCAN_CTA_TEMPLATES = {
        "fr": [
            "Découvrez-en plus dans notre bio 🔗",
            "Contactez-nous via DM ou WhatsApp",
            "Disponible maintenant — lien en bio",
            "Partagez avec vos proches ❤️",
            "Dites-nous en commentaire",
        ],
        "ar": [
            "اكتشف المزيد في البايو 🔗",
            "تواصل معنا عبر الرسائل المباشرة",
            "متوفر الآن — الرابط في البايو",
            "شاركها مع أحبائك ❤️",
            "أخبرنا في التعليقات",
        ],
        "en": [
            "More details in our bio 🔗",
            "DM us or WhatsApp",
            "Available now — link in bio",
            "Share with your friends ❤️",
            "Tell us in the comments",
        ],
    }

    def __init__(self, anthropic_api_key: str | None = None):
        self.anthropic_api_key = anthropic_api_key

    async def generate(
        self,
        platform: Platform,
        visual_description: str,
        brand_name: str,
        brand_guidelines: str = "",
        tone: ToneOfVoice = ToneOfVoice.BRAND,
        languages: list[str] = None,
        special_context: str = "",
        num_variants: int = 3,
        db: AsyncSession | None = None,
        user_id: str | None = None,
        session_id: str = "content-generation",
    ) -> GeneratedContent:
        """Generate multi-variant content for a given platform and visual."""
        if languages is None:
            languages = ["fr"]

        constraints = PLATFORM_CONSTRAINTS[platform]

        prompt = self._build_prompt(
            platform, visual_description, brand_name, brand_guidelines,
            tone, languages, special_context, num_variants, constraints
        )

        try:
            if not user_id:
                raise LLMConfigurationError("user_id is required for durable LLM orchestration")
            response = await get_llm_orchestrator().generate_text(
                LLMRequest(
                    user_message=prompt,
                    system_prompt=self._system_prompt(),
                    user_id=user_id,
                    session_id=session_id,
                    feature="content_generation",
                    persist_memory=True,
                    metadata={"platform": platform.value, "brand_name": brand_name},
                    max_tokens=2000,
                ),
                db=db,
            )
            raw = response.text
            data = self._parse_response(raw)
            return self._build_result(data, platform, tone, languages, constraints)
        except Exception as e:
            logger.error(f"Content generation failed: {e}")
            return self._fallback_content(platform, visual_description, languages)

    def _system_prompt(self) -> str:
        return """Tu es un expert en marketing digital spécialisé pour le marché marocain.
Tu crées des contenus engageants pour Instagram, TikTok, LinkedIn, Facebook et Twitter.
Tu maîtrises parfaitement le français, l'arabe darija et moderne, et l'anglais.
Tu comprends les nuances culturelles marocaines: Ramadan, Aïd, traditions, expressions locales.
Tu génères du contenu authentique qui résonne avec l'audience locale.
Réponds TOUJOURS en JSON valide, sans markdown ni backticks."""

    def _build_prompt(
        self, platform, description, brand, guidelines, tone, languages, context, n_variants, constraints
    ) -> str:
        lang_str = " + ".join(languages)
        return f"""Génère {n_variants} variantes de caption pour ce contenu:

PLATEFORME: {platform.value.upper()}
STYLE REQUIS: {constraints['style']}
LIMITE CARACTÈRES: {constraints['max_chars']}
MARQUE: {brand}
GUIDELINES: {guidelines or 'Ton professionnel et accessible'}
TON: {tone.value}
LANGUES: {lang_str}
CONTEXTE VISUEL: {description}
CONTEXTE SPÉCIAL: {context or 'Aucun'}

Retourne exactement ce JSON:
{{
  "captions": [
    {{
      "text": "texte complet de la caption",
      "language": "fr|ar|en",
      "emojis": ["emoji1", "emoji2"],
      "cta": "appel à l'action",
      "score": 75
    }}
  ],
  "hashtags": {{
    "trending": ["#hashtag1", "#hashtag2", "#hashtag3", "#hashtag4", "#hashtag5"],
    "niche": ["#niche1", "#niche2", "#niche3", "#niche4", "#niche5", "#niche6", "#niche7", "#niche8", "#niche9", "#niche10"],
    "branded": ["#BrandHashtag1", "#BrandHashtag2", "#BrandHashtag3", "#BrandHashtag4", "#BrandHashtag5"],
    "general": ["#general1", "#general2", "#general3", "#general4", "#general5", "#general6", "#general7", "#general8", "#general9", "#general10"]
  }}
}}"""

    def _parse_response(self, raw: str) -> dict:
        """Robust JSON parsing with cleanup."""
        text = raw.strip()
        # Strip markdown code blocks if present
        for prefix in ["```json", "```"]:
            if text.startswith(prefix):
                text = text[len(prefix):]
        text = text.rstrip("`").strip()
        text = self._extract_json_object(text)
        try:
            return json.loads(text)
        except json.JSONDecodeError as first_error:
            repaired = self._escape_control_chars_inside_strings(text)
            try:
                return json.loads(repaired)
            except json.JSONDecodeError as second_error:
                logger.warning("Content JSON repair fallback used: %s / %s", first_error, second_error)
                return self._best_effort_parse_response(repaired)

    def _extract_json_object(self, text: str) -> str:
        """Return the first balanced JSON object from an LLM response."""
        start = text.find("{")
        if start < 0:
            return text

        in_string = False
        escaped = False
        depth = 0
        for index in range(start, len(text)):
            char = text[index]
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start:index + 1]
        return text[start:]

    def _escape_control_chars_inside_strings(self, text: str) -> str:
        """Repair common LLM JSON issue: raw newlines/tabs inside string values."""
        repaired = []
        in_string = False
        escaped = False
        for char in text:
            if escaped:
                repaired.append(char)
                escaped = False
                continue
            if char == "\\":
                repaired.append(char)
                escaped = True
                continue
            if char == '"':
                repaired.append(char)
                in_string = not in_string
                continue
            if in_string and char in {"\n", "\r", "\t"}:
                repaired.append({"\n": "\\n", "\r": "\\r", "\t": "\\t"}[char])
                continue
            repaired.append(char)
        return "".join(repaired)

    def _best_effort_parse_response(self, text: str) -> dict:
        """Extract usable content from malformed LLM JSON instead of failing the request."""
        captions = []
        caption_blocks = re.findall(r'"text"\s*:\s*"([\s\S]*?)"\s*,\s*"language"\s*:\s*"([^"]*)"', text)
        for index, (caption_text, language) in enumerate(caption_blocks[:5]):
            cleaned_text = caption_text.replace('\\"', '"').replace("\\n", "\n").strip()
            if cleaned_text:
                captions.append(
                    {
                        "text": cleaned_text,
                        "language": language or "fr",
                        "emojis": [],
                        "cta": "",
                        "score": max(60, 80 - index * 4),
                    }
                )

        if not captions:
            plain = re.sub(r"[{}\[\]\"]", " ", text)
            plain = re.sub(r"\s+", " ", plain).strip()
            captions.append(
                {
                    "text": plain[:500] if plain else "Decouvrez notre nouvelle publication.",
                    "language": "fr",
                    "emojis": [],
                    "cta": "",
                    "score": 60,
                }
            )

        hashtags = list(dict.fromkeys(re.findall(r"#[\w\u0600-\u06ff_]+", text)))[:30]
        return {
            "captions": captions,
            "hashtags": {
                "trending": hashtags[:5],
                "niche": hashtags[5:15],
                "branded": [],
                "general": hashtags[15:30],
            },
        }

    def _build_result(self, data: dict, platform: Platform, tone: ToneOfVoice, languages: list[str], constraints: dict) -> GeneratedContent:
        captions = []
        for i, cap in enumerate(data.get("captions", [])):
            lang = cap.get("language", languages[0] if languages else "fr")
            text = cap.get("text", "")
            variant = CaptionVariant(
                text=text,
                platform=platform,
                tone=tone,
                language=lang,
                char_count=len(text),
                emojis=cap.get("emojis", []),
                call_to_action=cap.get("cta", ""),
                predicted_engagement_score=float(cap.get("score", 70)),
            )
            captions.append(variant)

        hashtag_data = data.get("hashtags", {})
        all_hashtags = []
        for cat_tags in hashtag_data.values():
            all_hashtags.extend(cat_tags)

        raw_with_scores = [
            {"tag": t, "category": cat, "score": 85 - i * 3}
            for cat, tags in hashtag_data.items()
            for i, t in enumerate(tags)
        ]

        best = max(captions, key=lambda c: c.predicted_engagement_score) if captions else captions[0] if captions else CaptionVariant("", platform, tone, "fr", 0, [], "", 70)

        ab_pairs = []
        if len(captions) >= 2:
            ab_pairs = [(captions[i], captions[i + 1]) for i in range(0, len(captions) - 1, 2)]

        return GeneratedContent(
            captions=captions,
            hashtags=all_hashtags,
            hashtag_categories=hashtag_data,
            raw_hashtags_with_scores=raw_with_scores,
            best_caption=best,
            ab_test_pairs=ab_pairs,
        )

    def _fallback_content(self, platform: Platform, description: str, languages: list[str]) -> GeneratedContent:
        lang = languages[0] if languages else "fr"
        fallback_text = {
            "fr": f"Découvrez notre dernière création ✨ {description[:100]}",
            "ar": f"اكتشف أحدث ابتكاراتنا ✨",
            "en": f"Discover our latest creation ✨",
        }.get(lang, description[:100])

        cap = CaptionVariant(
            text=fallback_text, platform=platform, tone=ToneOfVoice.BRAND,
            language=lang, char_count=len(fallback_text), emojis=["✨"],
            call_to_action="Lien en bio", predicted_engagement_score=60.0,
        )
        return GeneratedContent(
            captions=[cap], hashtags=["#maroc", "#marketing", "#digital"],
            hashtag_categories={}, raw_hashtags_with_scores=[],
            best_caption=cap, ab_test_pairs=[],
        )

    def to_dict(self, result: GeneratedContent) -> dict:
        return {
            "captions": [
                {
                    "text": c.text,
                    "platform": c.platform.value,
                    "tone": c.tone.value,
                    "language": c.language,
                    "char_count": c.char_count,
                    "emojis": c.emojis,
                    "cta": c.call_to_action,
                    "predicted_engagement_score": c.predicted_engagement_score,
                }
                for c in result.captions
            ],
            "hashtags": result.hashtags,
            "hashtag_categories": result.hashtag_categories,
            "best_caption_index": result.captions.index(result.best_caption) if result.captions else 0,
        }
