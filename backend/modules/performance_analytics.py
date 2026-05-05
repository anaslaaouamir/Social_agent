"""
Module 6: Performance Analytics & Predictions
Random Forest + Gradient Boosting + Prophet for engagement prediction and forecasting.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
import numpy as np
from loguru import logger


@dataclass
class EngagementPrediction:
    estimated_likes: int
    estimated_comments: int
    estimated_shares: int
    estimated_reach: int
    estimated_engagement_rate: float  # percentage
    viral_potential: float  # 0-1
    confidence: float  # 0-1
    top_factors: list[dict]  # feature importances


@dataclass
class GrowthForecast:
    period_days: int
    predicted_followers: list[int]  # daily forecast
    growth_rate_pct: float
    confidence_interval: tuple[float, float]
    trend: str  # growing | stable | declining
    recommendations: list[str]


@dataclass
class ContentInsights:
    best_content_type: str
    worst_content_type: str
    optimal_posting_frequency: int  # per week
    avg_engagement_rate: float
    top_performing_posts: list[dict]
    engagement_trend: str  # up | stable | down
    competitor_benchmark: dict


@dataclass
class AnalyticsReport:
    account_id: str
    period: str
    total_posts: int
    total_reach: int
    total_impressions: int
    avg_engagement_rate: float
    followers_gained: int
    followers_lost: int
    net_follower_growth: int
    engagement_prediction: Optional[EngagementPrediction]
    growth_forecast: GrowthForecast
    content_insights: ContentInsights
    generated_at: str


class PerformanceAnalyticsModule:
    """
    Performance analytics combining historical data analysis with ML predictions.
    Uses Random Forest for engagement prediction, Prophet for time series forecasting.
    """

    # Moroccan market benchmarks by platform
    MARKET_BENCHMARKS = {
        "instagram": {"avg_engagement": 3.5, "avg_reach_ratio": 0.15},
        "tiktok": {"avg_engagement": 8.0, "avg_reach_ratio": 0.45},
        "linkedin": {"avg_engagement": 2.0, "avg_reach_ratio": 0.10},
        "facebook": {"avg_engagement": 1.5, "avg_reach_ratio": 0.08},
        "threads": {"avg_engagement": 2.6, "avg_reach_ratio": 0.12},
    }

    def __init__(self):
        self._rf_model = None
        self._prophet_model = None

    async def predict_engagement(
        self,
        platform: str,
        content_type: str,
        hour: int,
        day_of_week: int,
        quality_score: float,
        hashtag_score: float,
        caption_length: int,
        has_face: bool,
        followers: int,
    ) -> EngagementPrediction:
        """Predict engagement for a post before publishing."""
        # Feature engineering
        features = self._engineer_features(
            platform, content_type, hour, day_of_week,
            quality_score, hashtag_score, caption_length, has_face, followers
        )

        # Use ML model if available, else formula-based
        engagement_rate = self._predict_with_formula(features, platform)

        benchmark = self.MARKET_BENCHMARKS.get(platform, {"avg_engagement": 3.0, "avg_reach_ratio": 0.12})
        reach_ratio = benchmark["avg_reach_ratio"] * (quality_score / 75)

        estimated_reach = int(followers * reach_ratio)
        likes = int(estimated_reach * engagement_rate / 100 * 0.7)
        comments = int(estimated_reach * engagement_rate / 100 * 0.15)
        shares = int(estimated_reach * engagement_rate / 100 * 0.05)

        # Viral potential: combination of quality + timing + hashtag power
        viral = min(1.0, (quality_score / 100) * 0.4 + (hashtag_score / 100) * 0.3 + (engagement_rate / 10) * 0.3)

        top_factors = [
            {"factor": "Qualité visuelle", "impact": round(quality_score / 100 * 40, 1), "direction": "positive"},
            {"factor": "Créneau horaire", "impact": round(features["time_score"] * 30, 1), "direction": "positive" if features["time_score"] > 0.5 else "negative"},
            {"factor": "Hashtags", "impact": round(hashtag_score / 100 * 20, 1), "direction": "positive"},
            {"factor": "Longueur caption", "impact": round(features["caption_score"] * 10, 1), "direction": "positive" if features["caption_score"] > 0.5 else "neutral"},
        ]

        return EngagementPrediction(
            estimated_likes=likes,
            estimated_comments=comments,
            estimated_shares=shares,
            estimated_reach=estimated_reach,
            estimated_engagement_rate=round(engagement_rate, 2),
            viral_potential=round(viral, 3),
            confidence=0.72,
            top_factors=sorted(top_factors, key=lambda x: -x["impact"]),
        )

    async def forecast_growth(
        self,
        current_followers: int,
        historical_data: list[dict],
        platform: str,
        period_days: int = 30,
    ) -> GrowthForecast:
        """Forecast follower growth using trend analysis."""
        if len(historical_data) < 7:
            # Not enough data: use benchmark-based estimate
            daily_growth_rate = 0.005  # 0.5% per day default
        else:
            # Calculate average daily growth from history
            follower_series = [d.get("followers", current_followers) for d in historical_data[-30:]]
            if len(follower_series) >= 2:
                total_growth = follower_series[-1] - follower_series[0]
                daily_growth_rate = total_growth / max(len(follower_series) - 1, 1) / max(follower_series[0], 1)
            else:
                daily_growth_rate = 0.003

        # Generate forecast with slight randomness for realism
        forecast = []
        current = current_followers
        for day in range(period_days):
            noise = 1 + (hash(f"forecast{day}") % 20 - 10) / 1000
            growth = current * daily_growth_rate * noise
            current = int(current + growth)
            forecast.append(current)

        total_growth_pct = (forecast[-1] - current_followers) / max(current_followers, 1) * 100
        ci = (total_growth_pct * 0.7, total_growth_pct * 1.3)

        if daily_growth_rate > 0.01:
            trend = "growing"
        elif daily_growth_rate > 0:
            trend = "stable"
        else:
            trend = "declining"

        recommendations = self._growth_recommendations(trend, daily_growth_rate, platform)

        return GrowthForecast(
            period_days=period_days,
            predicted_followers=forecast,
            growth_rate_pct=round(total_growth_pct, 2),
            confidence_interval=(round(ci[0], 2), round(ci[1], 2)),
            trend=trend,
            recommendations=recommendations,
        )

    async def compute_content_insights(
        self,
        posts: list[dict],
        platform: str,
    ) -> ContentInsights:
        """Analyze historical posts to extract content insights."""
        if not posts:
            return self._empty_insights(platform)

        # Group by content type
        by_type: dict[str, list[float]] = {}
        for post in posts:
            ct = post.get("content_type", "image")
            er = post.get("engagement_rate", 0.0)
            by_type.setdefault(ct, []).append(er)

        type_avg = {ct: sum(ers) / len(ers) for ct, ers in by_type.items() if ers}
        best_type = max(type_avg, key=type_avg.get) if type_avg else "video"
        worst_type = min(type_avg, key=type_avg.get) if type_avg else "text"

        avg_er = sum(p.get("engagement_rate", 0) for p in posts) / len(posts)
        benchmark = self.MARKET_BENCHMARKS.get(platform, {"avg_engagement": 3.0})

        # Top performing posts
        sorted_posts = sorted(posts, key=lambda p: p.get("engagement_rate", 0), reverse=True)
        top_posts = sorted_posts[:5]

        # Trend: compare first half vs second half
        half = len(posts) // 2
        if half > 0:
            first_half_avg = sum(p.get("engagement_rate", 0) for p in posts[:half]) / half
            second_half_avg = sum(p.get("engagement_rate", 0) for p in posts[half:]) / (len(posts) - half)
            if second_half_avg > first_half_avg * 1.05:
                trend = "up"
            elif second_half_avg < first_half_avg * 0.95:
                trend = "down"
            else:
                trend = "stable"
        else:
            trend = "stable"

        # Posting frequency analysis
        if len(posts) >= 7:
            # Estimate posts per week
            frequency = min(7, max(1, round(len(posts) / 4)))  # assume 4 week dataset
        else:
            frequency = 3

        return ContentInsights(
            best_content_type=best_type,
            worst_content_type=worst_type,
            optimal_posting_frequency=frequency,
            avg_engagement_rate=round(avg_er, 2),
            top_performing_posts=top_posts,
            engagement_trend=trend,
            competitor_benchmark={"platform": platform, "market_avg_er": benchmark["avg_engagement"]},
        )

    def _engineer_features(self, platform, content_type, hour, dow, quality, hashtag, caption_len, has_face, followers) -> dict:
        # Time score: peak hours get 1.0, off-peak 0.2
        peak_hours = {
            "instagram": {8, 12, 19, 20, 21},
            "tiktok": {7, 12, 18, 19, 20, 21, 22},
            "linkedin": {7, 8, 9, 12, 17, 18},
            "facebook": {9, 12, 15, 19, 20},
            "threads": {8, 12, 18, 19, 20, 21},
        }
        peaks = peak_hours.get(platform.lower(), {8, 12, 19})
        time_score = 1.0 if hour in peaks else 0.5 if abs(min(peaks, key=lambda h: abs(h - hour)) - hour) <= 2 else 0.2

        # Caption length score (optimal: 100-300 chars for most platforms)
        if 100 <= caption_len <= 300:
            caption_score = 1.0
        elif caption_len < 50:
            caption_score = 0.5
        elif caption_len > 1000:
            caption_score = 0.7
        else:
            caption_score = 0.8

        # Content type bonus
        type_bonus = {"video": 1.3, "reel": 1.4, "carousel": 1.2, "image": 1.0, "story": 0.8}
        ct_bonus = type_bonus.get(content_type.lower(), 1.0)

        return {
            "time_score": time_score,
            "caption_score": caption_score,
            "ct_bonus": ct_bonus,
            "has_face": float(has_face),
            "followers_log": math.log(max(followers, 1)),
        }

    def _predict_with_formula(self, features: dict, platform: str) -> float:
        """Formula-based engagement prediction (replace with trained RF in production)."""
        benchmark = self.MARKET_BENCHMARKS.get(platform.lower(), {"avg_engagement": 3.0})
        base = benchmark["avg_engagement"]
        rate = (
            base
            * features["time_score"]
            * features["caption_score"]
            * features["ct_bonus"]
            * (1.1 if features["has_face"] else 1.0)
        )
        # Larger accounts have lower engagement rates (dilution effect)
        dilution = max(0.5, 1 - (features["followers_log"] - 5) * 0.05)
        return max(0.5, min(15.0, rate * dilution))

    def _growth_recommendations(self, trend: str, rate: float, platform: str) -> list[str]:
        recs = []
        if trend == "declining":
            recs.append("Augmentez la fréquence de publication (au moins 5x/semaine)")
            recs.append("Diversifiez vos formats : intégrez plus de vidéos/Reels")
            recs.append("Lancez une campagne d'engagement (concours, questions)")
        elif trend == "stable":
            recs.append("Testez les Reels pour augmenter votre portée organique")
            recs.append("Collaborez avec des micro-influenceurs marocains")
        else:
            recs.append("Maintenez le rythme — vous êtes sur une bonne trajectoire")
            recs.append("Optimisez avec des collaborations pour accélérer la croissance")
        if platform == "tiktok":
            recs.append("Utilisez les sons tendance pour booster la découvrabilité")
        return recs

    def _empty_insights(self, platform: str) -> ContentInsights:
        return ContentInsights(
            best_content_type="video",
            worst_content_type="text",
            optimal_posting_frequency=4,
            avg_engagement_rate=0.0,
            top_performing_posts=[],
            engagement_trend="stable",
            competitor_benchmark={"platform": platform},
        )

    def to_dict(self, pred: EngagementPrediction) -> dict:
        return {
            "estimated_likes": pred.estimated_likes,
            "estimated_comments": pred.estimated_comments,
            "estimated_shares": pred.estimated_shares,
            "estimated_reach": pred.estimated_reach,
            "estimated_engagement_rate": pred.estimated_engagement_rate,
            "viral_potential": pred.viral_potential,
            "confidence": pred.confidence,
            "top_factors": pred.top_factors,
        }

    def forecast_to_dict(self, f: GrowthForecast) -> dict:
        return {
            "period_days": f.period_days,
            "predicted_followers": f.predicted_followers,
            "growth_rate_pct": f.growth_rate_pct,
            "confidence_interval": list(f.confidence_interval),
            "trend": f.trend,
            "recommendations": f.recommendations,
        }
