"""
Comprehensive test suite for Social Agent Platform.
Tests all 6 AI modules + API routes + services.
Run: pytest tests/ -v --cov=. --cov-report=term-missing
"""
from __future__ import annotations
import pytest
import asyncio
import json
import uuid
import time
from unittest.mock import AsyncMock, MagicMock, patch
from typing import AsyncGenerator

# ─── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_image_bytes():
    """Generate a minimal valid JPEG for testing."""
    from PIL import Image
    import io
    img = Image.new("RGB", (200, 200), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def sample_caption_fr():
    return "Découvrez notre nouvelle collection de produits artisanaux marocains ! Des couleurs vibrantes et une qualité exceptionnelle vous attendent. Disponible maintenant en livraison rapide partout au Maroc."


@pytest.fixture
def sample_caption_ar():
    return "اكتشف مجموعتنا الجديدة من المنتجات الحرفية المغربية! ألوان زاهية وجودة استثنائية في انتظارك. متوفر الآن مع توصيل سريع في جميع أنحاء المغرب."


# ─── Module 1: Computer Vision ─────────────────────────────────────────────

class TestComputerVisionModule:

    @pytest.mark.asyncio
    async def test_analyze_returns_result(self, sample_image_bytes):
        from modules.computer_vision import ComputerVisionModule
        module = ComputerVisionModule(anthropic_api_key="")
        result = await module.analyze(sample_image_bytes, filename="test.jpg")

        assert result is not None
        assert result.category in ["product", "lifestyle", "educational", "promotional", "event", "behind_scenes"]
        assert isinstance(result.content_tags, list)
        assert 0.0 <= result.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_color_palette_extraction(self, sample_image_bytes):
        from modules.computer_vision import ComputerVisionModule
        module = ComputerVisionModule()
        result = await module.analyze(sample_image_bytes)

        assert len(result.color_palette.dominant) >= 1
        # All dominant colors should be valid hex
        for color in result.color_palette.dominant:
            assert color.startswith("#"), f"Color {color} is not hex"
            assert len(color) == 7, f"Color {color} has wrong length"

    @pytest.mark.asyncio
    async def test_quality_score_range(self, sample_image_bytes):
        from modules.computer_vision import ComputerVisionModule
        module = ComputerVisionModule()
        result = await module.analyze(sample_image_bytes)

        assert 0.0 <= result.quality.overall_score <= 100.0
        assert 0.0 <= result.quality.sharpness <= 100.0
        assert 0.0 <= result.quality.exposure <= 100.0
        assert 0.0 <= result.quality.composition <= 100.0

    @pytest.mark.asyncio
    async def test_safety_check(self, sample_image_bytes):
        from modules.computer_vision import ComputerVisionModule
        module = ComputerVisionModule()
        result = await module.analyze(sample_image_bytes)

        # A plain color image should be safe
        assert result.is_safe is True
        assert result.safety_flags == []

    @pytest.mark.asyncio
    async def test_to_dict_serializable(self, sample_image_bytes):
        from modules.computer_vision import ComputerVisionModule
        module = ComputerVisionModule()
        result = await module.analyze(sample_image_bytes)
        d = module.to_dict(result)

        # Must be JSON serializable
        json_str = json.dumps(d)
        parsed = json.loads(json_str)
        assert parsed["category"] == result.category
        assert "quality" in parsed
        assert "color_palette" in parsed

    @pytest.mark.asyncio
    async def test_video_detection(self):
        from modules.computer_vision import ComputerVisionModule
        module = ComputerVisionModule()
        assert module._is_video("test.mp4") is True
        assert module._is_video("test.MOV") is True
        assert module._is_video("test.jpg") is False
        assert module._is_video("test.png") is False

    @pytest.mark.asyncio
    async def test_language_description_keys(self, sample_image_bytes):
        from modules.computer_vision import ComputerVisionModule
        # Mock Claude API to avoid real calls
        with patch.object(ComputerVisionModule, '_generate_description',
                         new=AsyncMock(return_value=("English desc", "Description FR", "وصف عربي"))):
            module = ComputerVisionModule()
            result = await module.analyze(sample_image_bytes)
            d = module.to_dict(result)
            assert "en" in d["descriptions"]
            assert "fr" in d["descriptions"]
            assert "ar" in d["descriptions"]


# ─── Module 2: Content Generation ──────────────────────────────────────────

class TestContentGenerationEngine:

    @pytest.mark.asyncio
    async def test_generate_returns_captions(self):
        from modules.content_generation import ContentGenerationEngine, Platform, ToneOfVoice
        mock_response = {
            "captions": [
                {"text": "Caption 1 ✨", "language": "fr", "emojis": ["✨"], "cta": "Lien en bio", "score": 75},
                {"text": "Caption 2 🔥", "language": "fr", "emojis": ["🔥"], "cta": "DM nous", "score": 82},
                {"text": "Caption 3 💯", "language": "fr", "emojis": ["💯"], "cta": "Voir bio", "score": 68},
            ],
            "hashtags": {
                "trending": ["#MarocDigital", "#Tendance", "#Innovation", "#Business", "#Marketing"],
                "niche": ["#ArtisanatMaroc", "#MadeInMaroc", "#QualitéMaroc", "#HandmadeMaroc", "#ProduitLocal",
                          "#Artisanat", "#Créatif", "#Original", "#Unique", "#Authentique"],
                "branded": ["#NotreMArque", "#Brand1", "#Brand2", "#Brand3", "#Brand4"],
                "general": ["#Maroc", "#Morocco", "#Lifestyle", "#Fashion", "#Style",
                            "#Beauty", "#Love", "#Happy", "#Life", "#Art"],
            }
        }

        with patch.object(ContentGenerationEngine, 'generate',
                         new=AsyncMock(return_value=None)) as mock_gen:
            engine = ContentGenerationEngine(anthropic_api_key="test-key")

            # Test the parser directly
            result = engine._build_result(mock_response, Platform.INSTAGRAM, ToneOfVoice.BRAND, ["fr"],
                                          {"max_chars": 2200})
            assert len(result.captions) == 3
            assert result.best_caption.predicted_engagement_score == 82
            assert len(result.hashtags) == 30

    @pytest.mark.asyncio
    async def test_platform_constraints_respected(self):
        from modules.content_generation import ContentGenerationEngine, Platform, PLATFORM_CONSTRAINTS
        engine = ContentGenerationEngine(anthropic_api_key="test-key")

        for platform in Platform:
            constraints = PLATFORM_CONSTRAINTS.get(platform)
            if constraints:
                assert "max_chars" in constraints
                assert "hashtag_limit" in constraints
                assert "style" in constraints

    @pytest.mark.asyncio
    async def test_fallback_content_not_empty(self):
        from modules.content_generation import ContentGenerationEngine, Platform
        engine = ContentGenerationEngine(anthropic_api_key="test-key")
        result = engine._fallback_content(Platform.INSTAGRAM, "Test description", ["fr"])

        assert len(result.captions) > 0
        assert result.best_caption is not None
        assert len(result.captions[0].text) > 0

    def test_json_parse_with_markdown(self):
        from modules.content_generation import ContentGenerationEngine, Platform
        engine = ContentGenerationEngine(anthropic_api_key="test-key")
        raw = '```json\n{"captions": [], "hashtags": {}}\n```'
        result = engine._parse_response(raw)
        assert result == {"captions": [], "hashtags": {}}

    def test_json_parse_clean(self):
        from modules.content_generation import ContentGenerationEngine
        engine = ContentGenerationEngine(anthropic_api_key="test-key")
        raw = '{"captions": [], "hashtags": {}}'
        result = engine._parse_response(raw)
        assert result["captions"] == []

    @pytest.mark.asyncio
    async def test_to_dict_structure(self):
        from modules.content_generation import ContentGenerationEngine, Platform, ToneOfVoice
        mock_response = {
            "captions": [{"text": "Test caption", "language": "fr", "emojis": [], "cta": "Bio", "score": 70}],
            "hashtags": {"trending": ["#Test"], "niche": [], "branded": [], "general": []},
        }
        engine = ContentGenerationEngine(anthropic_api_key="test-key")
        result = engine._build_result(mock_response, Platform.INSTAGRAM, ToneOfVoice.BRAND, ["fr"], {})
        d = engine.to_dict(result)

        assert "captions" in d
        assert "hashtags" in d
        assert "best_caption_index" in d
        # JSON serializable
        json.dumps(d)


# ─── Module 3: Hashtag Intelligence ────────────────────────────────────────

class TestHashtagIntelligenceSystem:

    @pytest.mark.asyncio
    async def test_recommend_returns_correct_structure(self):
        from modules.hashtag_intelligence import HashtagIntelligenceSystem
        system = HashtagIntelligenceSystem()
        rec = await system.recommend(
            caption="Nouveaux produits artisanaux marocains disponibles",
            platform="instagram",
            category="product",
            languages=["fr"],
            n_hashtags=25,
        )
        assert len(rec.all_hashtags) <= 25
        assert len(rec.all_hashtags) > 0
        assert rec.performance_score >= 0
        assert isinstance(rec.banned_detected, list)

    @pytest.mark.asyncio
    async def test_no_banned_in_final_set(self):
        from modules.hashtag_intelligence import HashtagIntelligenceSystem
        system = HashtagIntelligenceSystem()
        rec = await system.recommend(
            caption="Test",
            platform="instagram",
            category="lifestyle",
        )
        banned_in_final = [t for t in rec.all_hashtags if t.lower() in system.BANNED_HASHTAGS]
        assert banned_in_final == [], f"Banned hashtags in final set: {banned_in_final}"

    @pytest.mark.asyncio
    async def test_hashtags_are_proper_format(self):
        from modules.hashtag_intelligence import HashtagIntelligenceSystem
        system = HashtagIntelligenceSystem()
        rec = await system.recommend(caption="Test caption", platform="instagram", category="lifestyle")
        for tag in rec.all_hashtags:
            assert tag.startswith("#"), f"Tag {tag!r} doesn't start with #"
            assert len(tag) > 1, f"Tag {tag!r} is too short"

    def test_keyword_extraction(self):
        from modules.hashtag_intelligence import HashtagIntelligenceSystem
        system = HashtagIntelligenceSystem()
        text = "Nos produits artisanaux marocains sont disponibles maintenant avec livraison rapide"
        keywords = system._extract_keywords(text)
        assert len(keywords) > 0
        # Stopwords should be excluded
        assert "avec" not in keywords
        assert "sont" not in keywords

    @pytest.mark.asyncio
    async def test_moroccan_tags_in_result(self):
        from modules.hashtag_intelligence import HashtagIntelligenceSystem
        system = HashtagIntelligenceSystem()
        rec = await system.recommend(
            caption="Produit marocain unique",
            platform="instagram",
            category="product",
            languages=["fr"],
        )
        all_lower = {t.lower() for t in rec.all_hashtags}
        moroccan_lower = {t.lower() for tags in system.MOROCCAN_HASHTAGS.values() for t in tags}
        intersection = all_lower & moroccan_lower
        assert len(intersection) > 0, "No Moroccan-specific hashtags found in recommendations"

    @pytest.mark.asyncio
    async def test_deduplication(self):
        from modules.hashtag_intelligence import HashtagIntelligenceSystem
        system = HashtagIntelligenceSystem()
        rec = await system.recommend(caption="Test", platform="instagram", category="product")
        # No duplicate tags
        lower_tags = [t.lower() for t in rec.all_hashtags]
        assert len(lower_tags) == len(set(lower_tags)), "Duplicate hashtags found"

    @pytest.mark.asyncio
    async def test_to_dict_serializable(self):
        from modules.hashtag_intelligence import HashtagIntelligenceSystem
        system = HashtagIntelligenceSystem()
        rec = await system.recommend(caption="Test", platform="instagram", category="lifestyle")
        d = system.to_dict(rec)
        json.dumps(d)  # Must not raise


# ─── Module 4: Timing Predictor ────────────────────────────────────────────

class TestOptimalTimingPredictor:

    @pytest.mark.asyncio
    async def test_predict_returns_slots(self):
        from modules.timing_predictor import OptimalTimingPredictor
        predictor = OptimalTimingPredictor()
        pred = await predictor.predict(platform="instagram", content_type="image", account_id="test")

        assert len(pred.top_slots) == 5
        assert len(pred.weekly_heatmap) == 7
        assert len(pred.weekly_heatmap[0]) == 24

    @pytest.mark.asyncio
    async def test_heatmap_values_in_range(self):
        from modules.timing_predictor import OptimalTimingPredictor
        predictor = OptimalTimingPredictor()
        pred = await predictor.predict(platform="instagram", content_type="image", account_id="test")

        for day in pred.weekly_heatmap:
            for score in day:
                assert 0.0 <= score <= 100.0, f"Score {score} out of range"

    @pytest.mark.asyncio
    async def test_slot_scores_sorted_desc(self):
        from modules.timing_predictor import OptimalTimingPredictor
        predictor = OptimalTimingPredictor()
        pred = await predictor.predict(platform="instagram", content_type="image", account_id="test")

        scores = [s.predicted_engagement_score for s in pred.top_slots]
        assert scores == sorted(scores, reverse=True), "Slots not sorted by score"

    @pytest.mark.asyncio
    async def test_ramadan_adjustments(self):
        from modules.timing_predictor import OptimalTimingPredictor
        predictor = OptimalTimingPredictor()

        normal = await predictor.predict(platform="instagram", content_type="image", account_id="x", is_ramadan=False)
        ramadan = await predictor.predict(platform="instagram", content_type="image", account_id="x", is_ramadan=True)

        assert ramadan.ramadan_adjusted is True
        # Late night scores should be higher in Ramadan
        normal_midnight = normal.weekly_heatmap[0][23]
        ramadan_midnight = ramadan.weekly_heatmap[0][23]
        assert ramadan_midnight > normal_midnight, "Ramadan midnight should score higher"

    @pytest.mark.asyncio
    async def test_linkedin_weekend_lower(self):
        from modules.timing_predictor import OptimalTimingPredictor
        predictor = OptimalTimingPredictor()
        pred = await predictor.predict(platform="linkedin", content_type="image", account_id="test")

        # Weekday average should be higher than weekend for LinkedIn
        weekday_avg = sum(sum(pred.weekly_heatmap[d]) for d in range(5)) / 5
        weekend_avg = sum(sum(pred.weekly_heatmap[d]) for d in [5, 6]) / 2
        assert weekday_avg > weekend_avg, "LinkedIn weekday should outperform weekend"

    @pytest.mark.asyncio
    async def test_next_optimal_in_future(self):
        from modules.timing_predictor import OptimalTimingPredictor
        from datetime import datetime
        predictor = OptimalTimingPredictor()
        pred = await predictor.predict(platform="instagram", content_type="image", account_id="test")

        now = datetime.utcnow()
        assert pred.next_optimal > now, "next_optimal should be in the future"

    @pytest.mark.asyncio
    async def test_all_platforms(self):
        from modules.timing_predictor import OptimalTimingPredictor
        predictor = OptimalTimingPredictor()
        for platform in ["instagram", "tiktok", "linkedin", "facebook"]:
            pred = await predictor.predict(platform=platform, content_type="image", account_id="test")
            assert pred is not None
            assert len(pred.top_slots) > 0


# ─── Module 5: Sentiment Analysis ──────────────────────────────────────────

class TestSentimentAnalysisModule:

    @pytest.mark.asyncio
    async def test_positive_comment(self):
        from modules.sentiment_analysis import SentimentAnalysisModule, SentimentLabel
        module = SentimentAnalysisModule()
        result = await module.analyze_comment("Excellent produit ! Je suis vraiment content ❤️")
        assert result.sentiment in [SentimentLabel.POSITIVE, SentimentLabel.NEUTRAL]
        assert result.sentiment_score >= 0

    @pytest.mark.asyncio
    async def test_negative_comment(self):
        from modules.sentiment_analysis import SentimentAnalysisModule, SentimentLabel
        module = SentimentAnalysisModule()
        result = await module.analyze_comment("Horrible produit ! Je suis déçu, c'est une arnaque.")
        assert result.sentiment in [SentimentLabel.NEGATIVE, SentimentLabel.TOXIC]
        assert result.sentiment_score < 0

    @pytest.mark.asyncio
    async def test_arabic_comment(self, sample_caption_ar):
        from modules.sentiment_analysis import SentimentAnalysisModule
        module = SentimentAnalysisModule()
        result = await module.analyze_comment("منتج ممتاز! شكراً جزيلاً ❤️")
        assert result.language == "ar"
        assert result.sentiment_score >= 0

    @pytest.mark.asyncio
    async def test_question_detection(self):
        from modules.sentiment_analysis import SentimentAnalysisModule
        module = SentimentAnalysisModule()
        result = await module.analyze_comment("Quel est le prix ? C'est disponible au Maroc ?")
        assert result.is_question is True

    @pytest.mark.asyncio
    async def test_lead_detection(self):
        from modules.sentiment_analysis import SentimentAnalysisModule
        module = SentimentAnalysisModule()
        result = await module.analyze_comment("Quel est le prix et comment commander ?")
        assert result.is_lead is True

    @pytest.mark.asyncio
    async def test_toxic_detection(self):
        from modules.sentiment_analysis import SentimentAnalysisModule, SentimentLabel
        module = SentimentAnalysisModule()
        result = await module.analyze_comment("I hate stupid people")
        assert result.is_toxic is True
        assert result.auto_hide is True

    @pytest.mark.asyncio
    async def test_spam_detection(self):
        from modules.sentiment_analysis import SentimentAnalysisModule
        module = SentimentAnalysisModule()
        result = await module.analyze_comment("follow4follow please click link bit.ly/xyz")
        assert result.is_spam is True

    @pytest.mark.asyncio
    async def test_crisis_no_detection_below_threshold(self):
        from modules.sentiment_analysis import SentimentAnalysisModule, SentimentLabel
        from modules.sentiment_analysis import CommentAnalysis, Emotion, ReplyPriority
        module = SentimentAnalysisModule()

        # Mostly positive — no crisis
        positive_analyses = []
        for _ in range(10):
            a = await module.analyze_comment("Super produit !")
            positive_analyses.append(a)

        crisis = await module.detect_crisis(positive_analyses, baseline_volume=10)
        assert crisis.detected is False
        assert crisis.severity == "none"

    @pytest.mark.asyncio
    async def test_crisis_detection_above_threshold(self):
        from modules.sentiment_analysis import SentimentAnalysisModule
        module = SentimentAnalysisModule()

        # Mostly negative — should trigger crisis
        negative_texts = ["Horrible arnaque ! Déçu !", "Problème grave avec la commande", "Nul, jamais plus !"] * 10
        analyses = await module.analyze_batch(negative_texts)
        crisis = await module.detect_crisis(analyses, baseline_volume=5)

        # With 30 negative comments and baseline of 5, volume_spike = 6x
        assert crisis.volume_spike > 1.0

    @pytest.mark.asyncio
    async def test_batch_analysis(self):
        from modules.sentiment_analysis import SentimentAnalysisModule
        module = SentimentAnalysisModule()
        texts = ["Super !", "Problème ici", "Quel prix ?", "Merci beaucoup", "Arnaque totale"]
        results = await module.analyze_batch(texts)
        assert len(results) == len(texts)

    @pytest.mark.asyncio
    async def test_to_dict_all_fields(self):
        from modules.sentiment_analysis import SentimentAnalysisModule
        module = SentimentAnalysisModule()
        analysis = await module.analyze_comment("Super produit !")
        d = module.to_dict(analysis)
        required_keys = ["text", "language", "sentiment", "sentiment_score", "emotion",
                         "is_question", "is_lead", "is_toxic", "is_spam", "reply_priority",
                         "urgency_score", "entities", "topics", "suggested_reply", "auto_hide"]
        for key in required_keys:
            assert key in d, f"Missing key: {key}"
        json.dumps(d)


# ─── Module 6: Performance Analytics ───────────────────────────────────────

class TestPerformanceAnalyticsModule:

    @pytest.mark.asyncio
    async def test_predict_engagement_all_fields(self):
        from modules.performance_analytics import PerformanceAnalyticsModule
        module = PerformanceAnalyticsModule()
        pred = await module.predict_engagement(
            platform="instagram", content_type="image",
            hour=19, day_of_week=1, quality_score=85.0,
            hashtag_score=75.0, caption_length=150,
            has_face=True, followers=10000,
        )
        assert pred.estimated_likes >= 0
        assert pred.estimated_comments >= 0
        assert pred.estimated_reach >= 0
        assert 0.0 <= pred.viral_potential <= 1.0
        assert 0.0 <= pred.confidence <= 1.0
        assert 0.0 <= pred.estimated_engagement_rate <= 100.0
        assert len(pred.top_factors) > 0

    @pytest.mark.asyncio
    async def test_video_has_higher_prediction_than_image(self):
        from modules.performance_analytics import PerformanceAnalyticsModule
        module = PerformanceAnalyticsModule()
        base_kwargs = dict(
            platform="instagram", hour=19, day_of_week=1,
            quality_score=80.0, hashtag_score=70.0,
            caption_length=150, has_face=False, followers=10000,
        )
        image_pred = await module.predict_engagement(content_type="image", **base_kwargs)
        video_pred = await module.predict_engagement(content_type="video", **base_kwargs)
        assert video_pred.estimated_reach >= image_pred.estimated_reach

    @pytest.mark.asyncio
    async def test_peak_hour_beats_offpeak(self):
        from modules.performance_analytics import PerformanceAnalyticsModule
        module = PerformanceAnalyticsModule()
        base = dict(
            platform="instagram", content_type="image",
            day_of_week=1, quality_score=75.0,
            hashtag_score=70.0, caption_length=150,
            has_face=False, followers=10000,
        )
        peak = await module.predict_engagement(hour=20, **base)
        offpeak = await module.predict_engagement(hour=3, **base)
        assert peak.estimated_engagement_rate >= offpeak.estimated_engagement_rate

    @pytest.mark.asyncio
    async def test_growth_forecast_length(self):
        from modules.performance_analytics import PerformanceAnalyticsModule
        module = PerformanceAnalyticsModule()
        forecast = await module.forecast_growth(
            current_followers=5000, historical_data=[],
            platform="instagram", period_days=30,
        )
        assert len(forecast.predicted_followers) == 30
        assert forecast.predicted_followers[0] >= 5000

    @pytest.mark.asyncio
    async def test_growth_forecast_trend_labels(self):
        from modules.performance_analytics import PerformanceAnalyticsModule
        module = PerformanceAnalyticsModule()
        forecast = await module.forecast_growth(5000, [], "instagram", 7)
        assert forecast.trend in ["growing", "stable", "declining"]

    @pytest.mark.asyncio
    async def test_content_insights_empty(self):
        from modules.performance_analytics import PerformanceAnalyticsModule
        module = PerformanceAnalyticsModule()
        insights = await module.compute_content_insights([], "instagram")
        assert insights.avg_engagement_rate == 0.0
        assert insights.engagement_trend == "stable"

    @pytest.mark.asyncio
    async def test_content_insights_best_type(self):
        from modules.performance_analytics import PerformanceAnalyticsModule
        module = PerformanceAnalyticsModule()
        posts = [
            {"content_type": "video", "engagement_rate": 8.0},
            {"content_type": "video", "engagement_rate": 9.0},
            {"content_type": "image", "engagement_rate": 3.0},
            {"content_type": "image", "engagement_rate": 2.5},
        ]
        insights = await module.compute_content_insights(posts, "instagram")
        assert insights.best_content_type == "video"

    @pytest.mark.asyncio
    async def test_forecast_to_dict_serializable(self):
        from modules.performance_analytics import PerformanceAnalyticsModule
        module = PerformanceAnalyticsModule()
        forecast = await module.forecast_growth(1000, [], "tiktok", 14)
        d = module.forecast_to_dict(forecast)
        json.dumps(d)


# ─── DM Chatbot Service ─────────────────────────────────────────────────────

class TestDMChatbotService:

    @pytest.mark.asyncio
    async def test_intent_detection_fr(self):
        from services.dm_chatbot import DMChatbotService, Intent
        service = DMChatbotService(anthropic_api_key="test")
        assert service._detect_intent("Quel est le prix ?") == Intent.PRICE_REQUEST
        assert service._detect_intent("Bonjour !") == Intent.GREETING
        assert service._detect_intent("J'ai un problème avec ma commande") == Intent.COMPLAINT

    @pytest.mark.asyncio
    async def test_intent_detection_ar(self):
        from services.dm_chatbot import DMChatbotService, Intent
        service = DMChatbotService(anthropic_api_key="test")
        assert service._detect_intent("بشحال هذا المنتج؟") == Intent.PRICE_REQUEST
        assert service._detect_intent("السلام عليكم") == Intent.GREETING

    def test_language_detection(self):
        from services.dm_chatbot import DMChatbotService
        service = DMChatbotService(anthropic_api_key="test")
        assert service._detect_language("Bonjour comment allez-vous ?") == "fr"
        assert service._detect_language("مرحبا كيف حالك؟") == "ar"
        assert service._detect_language("Hello how are you") == "en"

    @pytest.mark.asyncio
    async def test_fallback_message_languages(self):
        from services.dm_chatbot import DMChatbotService
        service = DMChatbotService(anthropic_api_key="test")
        assert "Merci" in service._fallback_message("fr")
        assert "شكراً" in service._fallback_message("ar")
        assert "Thank" in service._fallback_message("en")


# ─── Social Publisher Service ───────────────────────────────────────────────

class TestSocialPublisherService:

    @pytest.mark.asyncio
    async def test_mock_publish_all_platforms(self):
        from services.social_publisher import SocialPublisherService, PublishStatus
        service = SocialPublisherService()  # No tokens = mock mode

        for platform in ["tiktok", "linkedin"]:
            result = await service.publish_to_platform(
                platform=platform,
                caption="Test caption",
                media_urls=["https://example.com/img.jpg"],
                content_type="image",
            )
            assert result.status == PublishStatus.SUCCESS
            assert result.platform_post_id is not None
            assert result.platform_post_id.startswith(f"mock_{platform}_")

    @pytest.mark.asyncio
    async def test_instagram_without_credentials_returns_auth_error(self):
        from services.social_publisher import SocialPublisherService, PublishStatus

        service = SocialPublisherService()
        result = await service.publish_to_platform(
            platform="instagram",
            caption="Test caption",
            media_urls=["https://example.com/img.jpg"],
            content_type="image",
        )

        assert result.status == PublishStatus.AUTH_ERROR
        assert result.platform_post_id is None
        assert result.published_at is None

    @pytest.mark.asyncio
    async def test_facebook_without_credentials_returns_auth_error(self):
        from services.social_publisher import SocialPublisherService, PublishStatus

        service = SocialPublisherService()
        result = await service.publish_to_platform(
            platform="facebook",
            caption="Test caption",
            media_urls=["https://example.com/img.jpg"],
            content_type="image",
        )

        assert result.status == PublishStatus.AUTH_ERROR
        assert result.platform_post_id is None
        assert result.published_at is None

    @pytest.mark.asyncio
    async def test_multi_platform_concurrent(self):
        from services.social_publisher import SocialPublisherService, PublishStatus
        service = SocialPublisherService()

        results = await service.publish_multi_platform(
            platforms=["instagram", "tiktok", "facebook"],
            caption="Test multi-platform",
            media_urls=[],
        )
        assert len(results) == 3
        assert results[0].status == PublishStatus.AUTH_ERROR
        assert results[1].status == PublishStatus.SUCCESS
        assert results[2].status == PublishStatus.AUTH_ERROR

    @pytest.mark.asyncio
    async def test_unknown_platform_returns_failed(self):
        from services.social_publisher import SocialPublisherService, PublishStatus
        service = SocialPublisherService()
        result = await service.publish_to_platform("twitter_v2_unsupported", "Test", [])
        assert result.status == PublishStatus.FAILED

    @pytest.mark.asyncio
    async def test_twitter_media_without_oauth1_credentials_returns_failed(self):
        from services.social_publisher import SocialPublisherService, PublishStatus

        service = SocialPublisherService(
            twitter_token="token-123",
            twitter_user_id="user-456",
        )

        result = await service.publish_to_platform(
            platform="twitter",
            caption="Test with media",
            media_urls=["data:image/png;base64,aGVsbG8="],
            content_type="image",
        )

        assert result.status == PublishStatus.FAILED
        assert "OAuth 1.0a media upload is not fully configured" in (result.error_message or "")

    @pytest.mark.asyncio
    async def test_publish_result_has_timestamp(self):
        from services.social_publisher import SocialPublisherService, PublishStatus
        service = SocialPublisherService()
        result = service._mock_publish("instagram")
        assert result.published_at is not None
        assert result.published_at <= time.time()

    @pytest.mark.asyncio
    async def test_facebook_publish_uses_post_body_not_query_params(self):
        from services.social_publisher import SocialPublisherService, PublishStatus

        class DummyResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"id": "fb_post_123"}

        class DummyClient:
            def __init__(self):
                self.calls = []

            async def post(self, url, **kwargs):
                self.calls.append((url, kwargs))
                return DummyResponse()

        service = SocialPublisherService(
            facebook_token="token-123",
            facebook_page_id="page-456",
        )
        dummy_client = DummyClient()
        service._client = dummy_client

        result = await service.publish_to_platform(
            platform="facebook",
            caption="Caption " * 200,
            media_urls=["https://example.com/image.jpg"],
            content_type="image",
        )

        assert result.status == PublishStatus.SUCCESS
        assert len(dummy_client.calls) == 1
        url, kwargs = dummy_client.calls[0]
        assert url.endswith("/page-456/photos")
        assert "data" in kwargs
        assert "params" not in kwargs
        assert kwargs["data"]["access_token"] == "token-123"
        assert kwargs["data"]["url"] == "https://example.com/image.jpg"

    @pytest.mark.asyncio
    async def test_instagram_data_url_uses_signed_media_proxy_when_post_id_is_provided(self):
        from services.social_publisher import SocialPublisherService

        service = SocialPublisherService(
            instagram_token="token-123",
            instagram_account_id="ig-456",
        )
        service._settings.public_api_base_url = "https://example-public.test"

        url = await service._prepare_non_facebook_media_url(
            "instagram",
            "data:image/png;base64,aGVsbG8=",
            post_id="post-123",
            media_index=0,
        )

        assert url.startswith("https://example-public.test/api/posts/post-123/media/0?")
        assert "token=" in url
        assert "expires=" in url

    def test_signed_media_proxy_url_uses_posts_endpoint(self):
        from services.social_publisher import SocialPublisherService

        service = SocialPublisherService(
            instagram_token="token-123",
            instagram_account_id="ig-456",
        )
        service._settings.public_api_base_url = "https://example-public.test"

        url = service._build_signed_media_proxy_url(
            "post-123",
            0,
            "data:image/png;base64,aGVsbG8=",
        )

        assert url.startswith("https://example-public.test/api/posts/post-123/media/0?")
        assert "token=" in url
        assert "expires=" in url


# ─── Integration-style tests (no DB, no external calls) ────────────────────

class TestModulePipeline:
    """End-to-end pipeline: image → analysis → content → hashtags → timing."""

    @pytest.mark.asyncio
    async def test_full_content_pipeline(self, sample_image_bytes):
        from modules.computer_vision import ComputerVisionModule
        from modules.hashtag_intelligence import HashtagIntelligenceSystem
        from modules.timing_predictor import OptimalTimingPredictor

        # Step 1: Analyze image
        cv_module = ComputerVisionModule()
        visual = await cv_module.analyze(sample_image_bytes, "product.jpg")
        assert visual is not None

        # Step 2: Get hashtags based on category
        hashtag_system = HashtagIntelligenceSystem()
        rec = await hashtag_system.recommend(
            caption=visual.description_fr or "Produit",
            platform="instagram",
            category=visual.category,
        )
        assert len(rec.all_hashtags) > 0

        # Step 3: Get timing
        predictor = OptimalTimingPredictor()
        timing = await predictor.predict("instagram", visual.content_tags[0] if visual.content_tags else "image", "acc1")
        assert len(timing.top_slots) > 0

    @pytest.mark.asyncio
    async def test_sentiment_to_crisis_pipeline(self):
        from modules.sentiment_analysis import SentimentAnalysisModule
        module = SentimentAnalysisModule()

        comments = [
            "Produit de mauvaise qualité, déçu",
            "Problème avec la livraison !",
            "Arnaque totale, je veux un remboursement",
            "Jamais vu un service aussi nul",
            "Horrible, je ne recommande pas",
        ] * 6  # 30 total negative comments

        analyses = await module.analyze_batch(comments)
        crisis = await module.detect_crisis(analyses, baseline_volume=10)

        assert crisis.volume_spike > 1.0
        assert crisis.negative_ratio > 0.5


def test_dataset_loader_clean_text():
    from services.dataset_loader import clean_text

    assert clean_text("Visitez http://spam.com @user #test") == "Visitez test"
    assert clean_text("  bonjour  ") == "bonjour"


def test_dataset_loader_features():
    import pandas as pd
    from services.dataset_loader import extract_text_features

    df = pd.DataFrame({"text": ["Hello world! #test @user", "Simple post"]})
    df = extract_text_features(df)
    assert "hashtag_count" in df.columns
    assert df.loc[0, "hashtag_count"] == 1
    assert df.loc[0, "has_mention"] == 1


def test_engagement_predictor_heuristic():
    from services.ml_engagement import EngagementPredictor

    pred = EngagementPredictor()
    result = pred.predict(
        platform="instagram",
        content_type="reel",
        hour=19,
        day_of_week=2,
    )
    assert 0 < result.predicted_engagement_rate < 0.5
    assert result.confidence >= 0.4


def test_nlp_spam_detection():
    from services.nlp_pipeline import NLPPipeline

    pipeline = NLPPipeline()
    is_spam, score = pipeline.detect_spam("Buy followers! check my bio dm for promo")
    assert is_spam
    assert score > 0.5
    is_clean, _ = pipeline.detect_spam("Belle photo, j'adore!")
    assert not is_clean


def test_nlp_unified_label():
    from services.nlp_pipeline import NLPPipeline, NLPResult

    pipeline = NLPPipeline()
    spam_result = NLPResult(
        text="spam",
        is_spam=True,
        spam_score=0.9,
        is_toxic=False,
        toxic_score=0.1,
        sentiment="negative",
        sentiment_score=-0.5,
        topic_id=-1,
        topic_label="",
        topic_keywords=[],
        language="en",
    )
    assert pipeline.get_unified_label(spam_result) == "spam"


@pytest.mark.asyncio
async def test_nlp_pipeline_process():
    from services.nlp_pipeline import NLPPipeline

    pipeline = NLPPipeline()
    result = await pipeline.process("J'adore ce produit, excellent!")
    assert result.sentiment in ("positive", "neutral", "negative")
    assert 0.0 <= result.spam_score <= 1.0
    assert result.language != ""


def test_matches_inbox_kind_filters_real_dms():
    from api.routes.dm import _matches_inbox_kind

    dm_item = {"source_type": "dm"}
    comment_item = {"source_type": "comment"}

    assert _matches_inbox_kind(dm_item, "all") is True
    assert _matches_inbox_kind(comment_item, "all") is True
    assert _matches_inbox_kind(dm_item, "dm") is True
    assert _matches_inbox_kind(comment_item, "dm") is False
    assert _matches_inbox_kind(dm_item, "interactions") is False
    assert _matches_inbox_kind(comment_item, "interactions") is True
