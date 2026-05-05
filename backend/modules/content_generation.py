"""
Module 2: Content Generation Engine
Generates platform-optimized captions, hashtags, and variants using Claude.
Supports FR/AR/EN with Moroccan cultural context.
"""
from __future__ import annotations
import json
import asyncio
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
from loguru import logger


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

    def __init__(self, anthropic_api_key: str):
        import anthropic
        self.client = anthropic.AsyncAnthropic(api_key=anthropic_api_key)

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
            response = await self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                system=self._system_prompt(),
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text
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
        return json.loads(text)

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
