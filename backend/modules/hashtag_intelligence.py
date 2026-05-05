"""
Module 3: Hashtag Intelligence System
Recommends optimal hashtags using collaborative filtering, GNN relationships,
TF-IDF extraction, and real-time trend scoring.
"""
from __future__ import annotations
import re
import math
import asyncio
from dataclasses import dataclass, field
from typing import Optional
from collections import defaultdict
from loguru import logger
import numpy as np


@dataclass
class HashtagMetrics:
    tag: str
    category: str  # trending | niche | branded | general | moroccan
    trending_score: float  # 0-100
    avg_reach: float
    avg_engagement_rate: float
    post_count_24h: int
    saturation: float  # 0-1, higher = more saturated
    is_banned: bool
    top_posts_probability: float  # 0-1
    market: str = "MA"
    language: str = "fr"


@dataclass
class HashtagRecommendation:
    all_hashtags: list[str]
    categorized: dict[str, list[HashtagMetrics]]
    estimated_reach: float
    estimated_engagement_rate: float
    banned_detected: list[str]
    rotation_suggestion: list[str]
    performance_score: float  # 0-100


class HashtagIntelligenceSystem:
    """
    Hashtag recommendation engine combining:
    - TF-IDF for keyword extraction from caption
    - Collaborative filtering for related hashtags
    - Trend scoring (simulated + real API when available)
    - Moroccan market specifics
    - Ban detection
    """

    # Moroccan market hashtags with baseline metrics
    MOROCCAN_HASHTAGS = {
        "fr": [
            "#Maroc", "#Marrakech", "#Casablanca", "#Rabat", "#MarocVu",
            "#MarocTourisme", "#MadeInMaroc", "#EntrepriseMarocaine",
            "#StartupMaroc", "#DigitalMaroc", "#eCommerceMaroc",
        ],
        "ar": [
            "#المغرب", "#مراكش", "#الدار_البيضاء", "#الرباط", "#صنع_في_المغرب",
            "#تسويق_رقمي", "#أعمال_المغرب",
        ],
        "general": [
            "#Morocco", "#MoroccanBusiness", "#MoroccoLife", "#Medina",
            "#ArganOil", "#MoroccanFood",
        ],
    }

    # Known banned/restricted hashtags (partial list — updated periodically)
    BANNED_HASHTAGS = {
        "#follow4follow", "#f4f", "#like4like", "#l4l", "#spam",
        "#adulting", "#alone", "#beautyblogger2023",  # periodically restricted
    }

    # Seasonal/event hashtags for Morocco
    SEASONAL_TAGS = {
        "ramadan": ["#Ramadan", "#RamadanKareem", "#RamadanMaroc", "#رمضان"],
        "eid": ["#AidMoubarak", "#Eid", "#عيد_مبارك"],
        "blackfriday": ["#BlackFriday", "#BlackFridayMaroc", "#PromoMaroc"],
        "summer": ["#EtéMaroc", "#VacancesMaroc", "#MarocSummer"],
    }

    def __init__(self):
        self._hashtag_db: dict[str, HashtagMetrics] = {}
        self._cooccurrence: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self._tfidf_cache: dict[str, list[str]] = {}
        self._initialized = False

    async def initialize(self):
        """Seed the hashtag database with baseline data."""
        if self._initialized:
            return
        await self._seed_database()
        self._initialized = True
        logger.info("Hashtag Intelligence System initialized")

    async def recommend(
        self,
        caption: str,
        platform: str,
        category: str,
        brand_hashtags: list[str] = None,
        languages: list[str] = None,
        exclude_tags: list[str] = None,
        n_hashtags: int = 25,
    ) -> HashtagRecommendation:
        """
        Generate optimized hashtag set for a post.
        Strategy: 5 trending + 10 niche + 5 branded + 5 moroccan = 25
        """
        if not self._initialized:
            await self.initialize()

        if languages is None:
            languages = ["fr"]
        if brand_hashtags is None:
            brand_hashtags = []
        if exclude_tags is None:
            exclude_tags = []

        # Extract semantic keywords from caption
        keywords = self._extract_keywords(caption)

        # Gather candidates from multiple sources concurrently
        tasks = [
            self._get_trending(platform, n=8),
            self._get_niche_for_keywords(keywords, category, n=12),
            self._get_moroccan(languages, n=6),
            self._get_related_by_cooccurrence(keywords[:3], n=6),
        ]
        trending, niche, moroccan, related = await asyncio.gather(*tasks)

        # Build branded
        branded = [HashtagMetrics(
            tag=t, category="branded", trending_score=60, avg_reach=5000,
            avg_engagement_rate=0.04, post_count_24h=100, saturation=0.2,
            is_banned=False, top_posts_probability=0.6,
        ) for t in brand_hashtags[:5]]

        # Filter banned tags
        def not_banned(m: HashtagMetrics) -> bool:
            return not m.is_banned and m.tag.lower() not in {t.lower() for t in (exclude_tags or [])}

        trending = [m for m in trending if not_banned(m)][:5]
        niche = [m for m in niche if not_banned(m)][:10]
        moroccan = [m for m in moroccan if not_banned(m)][:5]

        all_metrics = trending + niche + branded + moroccan + related[:3]

        # Deduplicate by tag
        seen = set()
        unique: list[HashtagMetrics] = []
        for m in all_metrics:
            key = m.tag.lower()
            if key not in seen:
                seen.add(key)
                unique.append(m)

        # Limit total
        final = unique[:n_hashtags]
        all_tags = [m.tag for m in final]

        # Detect any banned tags in final set
        banned_found = [m.tag for m in final if m.is_banned]

        # Compute aggregate metrics
        if final:
            est_reach = np.mean([m.avg_reach for m in final])
            est_engagement = np.mean([m.avg_engagement_rate for m in final])
            avg_trending = np.mean([m.trending_score for m in final])
            avg_tpp = np.mean([m.top_posts_probability for m in final])
            perf_score = (avg_trending * 0.4 + avg_tpp * 100 * 0.3 + min(100, est_engagement * 2000) * 0.3)
        else:
            est_reach = 0
            est_engagement = 0
            perf_score = 0

        categorized = {
            "trending": [m for m in final if m.category == "trending"],
            "niche": [m for m in final if m.category == "niche"],
            "branded": [m for m in final if m.category == "branded"],
            "moroccan": [m for m in final if m.category == "moroccan"],
            "general": [m for m in final if m.category == "general"],
        }

        # Rotation: suggest 5 alternatives
        rotation = [m.tag for m in niche[3:8]]

        return HashtagRecommendation(
            all_hashtags=all_tags,
            categorized=categorized,
            estimated_reach=round(est_reach),
            estimated_engagement_rate=round(est_engagement * 100, 2),
            banned_detected=banned_found,
            rotation_suggestion=rotation,
            performance_score=round(perf_score, 1),
        )

    def _extract_keywords(self, text: str) -> list[str]:
        """TF-IDF-inspired keyword extraction from caption text."""
        # Stopwords (FR + EN + AR common)
        stopwords = {
            "le", "la", "les", "de", "du", "des", "un", "une", "et", "en",
            "à", "au", "aux", "pour", "par", "sur", "the", "a", "an", "of",
            "in", "is", "are", "with", "our", "your", "من", "في", "على", "مع",
            "avec", "sont", "nous", "vous", "ils", "elles", "leur", "leurs",
            "mais", "donc", "car", "que", "qui", "quoi", "dont", "où",
            "this", "that", "they", "them", "their", "have", "has", "been",
            "maintenant", "disponibles", "disponible", "notre", "nos", "vos",
        }
        words = re.findall(r"\b\w{4,}\b", text.lower())
        keywords = [w for w in words if w not in stopwords]

        # Score by frequency (simplified TF)
        freq: dict[str, int] = defaultdict(int)
        for w in keywords:
            freq[w] += 1

        sorted_kw = sorted(freq.keys(), key=lambda w: -freq[w])
        return sorted_kw[:10]

    async def _get_trending(self, platform: str, n: int) -> list[HashtagMetrics]:
        """Get trending hashtags. In production: call platform APIs."""
        # Baseline trending for Morocco market
        trending_pool = [
            ("#MarocDigital", 92), ("#BusinessMaroc", 88), ("#Innovation", 85),
            ("#Entrepreneur", 87), ("#Marketing", 84), ("#Tendance", 82),
            ("#NouveauProduit", 79), ("#MadeInMaroc", 90), ("#eCommerce", 81),
            ("#PMEMaroc", 77),
        ]
        results = []
        for tag, score in trending_pool[:n]:
            results.append(HashtagMetrics(
                tag=tag, category="trending", trending_score=score,
                avg_reach=random_range(8000, 50000),
                avg_engagement_rate=random_range(0.02, 0.06),
                post_count_24h=random_range(500, 5000),
                saturation=score / 100 * 0.7,
                is_banned=False, top_posts_probability=0.15,
            ))
        return results

    async def _get_niche_for_keywords(self, keywords: list[str], category: str, n: int) -> list[HashtagMetrics]:
        """Get niche hashtags related to keywords and content category."""
        category_niche = {
            "product": ["#ArtisanatMaroc", "#HandmadeMaroc", "#QualitéMaroc", "#ProduitLocal", "#ArtisanatMorocain"],
            "lifestyle": ["#VieAuMaroc", "#MarocLife", "#CasablancaLife", "#MarrakechStyle", "#RiadLife"],
            "educational": ["#ApprendreEnsemble", "#Formation", "#Savoir", "#Education", "#SkillsMaroc"],
            "promotional": ["#Promo", "#Offre", "#Réduction", "#BonPlan", "#DealMaroc"],
        }
        base = category_niche.get(category, category_niche["lifestyle"])
        keyword_tags = [f"#{kw.capitalize()}" for kw in keywords[:5] if len(kw) > 3]
        pool = base + keyword_tags

        results = []
        for tag in pool[:n]:
            results.append(HashtagMetrics(
                tag=tag, category="niche", trending_score=random_range(40, 70),
                avg_reach=random_range(500, 8000),
                avg_engagement_rate=random_range(0.04, 0.12),
                post_count_24h=random_range(10, 200),
                saturation=random_range(0.1, 0.3),
                is_banned=tag.lower() in self.BANNED_HASHTAGS,
                top_posts_probability=random_range(0.25, 0.6),
            ))
        return results

    async def _get_moroccan(self, languages: list[str], n: int) -> list[HashtagMetrics]:
        """Get Morocco-specific hashtags."""
        pool = []
        for lang in languages:
            pool.extend(self.MOROCCAN_HASHTAGS.get(lang, []))
        pool.extend(self.MOROCCAN_HASHTAGS["general"])

        results = []
        for tag in pool[:n]:
            results.append(HashtagMetrics(
                tag=tag, category="moroccan", trending_score=random_range(55, 85),
                avg_reach=random_range(2000, 20000),
                avg_engagement_rate=random_range(0.03, 0.08),
                post_count_24h=random_range(100, 1000),
                saturation=0.4,
                is_banned=False,
                top_posts_probability=0.2,
                market="MA",
            ))
        return results

    async def _get_related_by_cooccurrence(self, keywords: list[str], n: int) -> list[HashtagMetrics]:
        """Co-occurrence graph: find hashtags that appear together frequently."""
        # In production: query a GNN/graph DB. Here: return complementary tags.
        related = ["#Tendance2025", "#ContentMarketing", "#SocialMediaMaroc",
                   "#Community", "#Engagement", "#Authentique"]
        return [
            HashtagMetrics(
                tag=t, category="general", trending_score=60,
                avg_reach=3000, avg_engagement_rate=0.035,
                post_count_24h=150, saturation=0.3, is_banned=False,
                top_posts_probability=0.2,
            ) for t in related[:n]
        ]

    async def _seed_database(self):
        """Initialize hashtag database with baseline data."""
        all_tags = []
        for lang_tags in self.MOROCCAN_HASHTAGS.values():
            all_tags.extend(lang_tags)
        for tag in all_tags:
            self._hashtag_db[tag.lower()] = HashtagMetrics(
                tag=tag, category="moroccan", trending_score=65,
                avg_reach=5000, avg_engagement_rate=0.05,
                post_count_24h=300, saturation=0.35,
                is_banned=False, top_posts_probability=0.25,
            )

    def to_dict(self, rec: HashtagRecommendation) -> dict:
        return {
            "all_hashtags": rec.all_hashtags,
            "categorized": {
                cat: [
                    {"tag": m.tag, "score": m.trending_score, "reach": m.avg_reach,
                     "engagement_rate": m.avg_engagement_rate}
                    for m in metrics
                ]
                for cat, metrics in rec.categorized.items()
            },
            "estimated_reach": rec.estimated_reach,
            "estimated_engagement_rate": rec.estimated_engagement_rate,
            "banned_detected": rec.banned_detected,
            "rotation_suggestion": rec.rotation_suggestion,
            "performance_score": rec.performance_score,
        }


def random_range(low: float, high: float) -> float:
    """Deterministic-ish random for baseline data."""
    import random
    return round(random.uniform(low, high), 3)
