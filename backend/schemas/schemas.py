"""Pydantic schemas — request/response validation for all API endpoints."""
from __future__ import annotations
from typing import Optional, Any
from pydantic import BaseModel, EmailStr, Field, field_validator
from datetime import datetime


# ─── Auth ────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str = Field(..., min_length=2, max_length=100)


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str
    is_active: bool
    preferred_language: str
    model_config = {"from_attributes": True}


# ─── Social Accounts ─────────────────────────────────────────────────────────

PLATFORM_PATTERN = "^(instagram|tiktok|linkedin|facebook|twitter|threads|youtube|pinterest)$"


class AccountCreate(BaseModel):
    platform: str = Field(..., pattern=PLATFORM_PATTERN)
    account_id: str
    account_name: str
    access_token: str
    refresh_token: str = ""
    followers_count: int = Field(0, ge=0)


class AccountOut(BaseModel):
    id: str
    platform: str
    account_name: str
    account_id: str
    followers_count: int
    model_config = {"from_attributes": True}


# ─── Posts ───────────────────────────────────────────────────────────────────

class PostCreate(BaseModel):
    account_id: str
    content_type: str = Field("image", pattern="^(image|video|carousel|reel|story)$")
    caption: Optional[str] = Field(None, max_length=10000)
    hashtags: list[str] = Field(default_factory=list, max_length=50)
    media_urls: list[str] = Field(default_factory=list)
    scheduled_at: Optional[float] = None

    @field_validator("hashtags")
    @classmethod
    def validate_hashtags(cls, v: list[str]) -> list[str]:
        return [tag if tag.startswith("#") else f"#{tag}" for tag in v]


class PostUpdate(BaseModel):
    caption: Optional[str] = Field(None, max_length=10000)
    hashtags: Optional[list[str]] = None
    scheduled_at: Optional[float] = None
    status: Optional[str] = None


class PostOut(BaseModel):
    id: str
    account_id: str
    content_type: str
    status: str
    caption: Optional[str]
    hashtags: list
    media_urls: list
    scheduled_at: Optional[float]
    published_at: Optional[float]
    platform_post_id: Optional[str]
    ai_quality_score: Optional[float]
    ai_predicted_engagement: Optional[float]
    likes_count: int
    comments_count: int
    shares_count: int
    reach: int
    engagement_rate: float
    visual_analysis: dict
    ai_caption_variants: list
    model_config = {"from_attributes": True}



# ─── Content Generation ──────────────────────────────────────────────────────

class ContentGenerateRequest(BaseModel):
    platform: str = Field(..., pattern=PLATFORM_PATTERN)
    visual_description: str = Field(..., min_length=10, max_length=2000)
    brand_name: str = Field("", max_length=100)
    brand_guidelines: str = Field("", max_length=1000)
    tone: str = Field("brand", pattern="^(brand|fun|informative|promotional|inspirational)$")
    languages: list[str] = Field(["fr"])
    special_context: str = Field("", max_length=500)
    num_variants: int = Field(3, ge=1, le=5)


class CaptionVariantOut(BaseModel):
    text: str
    platform: str
    tone: str
    language: str
    char_count: int
    emojis: list[str]
    cta: str
    predicted_engagement_score: float


class ContentGenerateOut(BaseModel):
    captions: list[CaptionVariantOut]
    hashtags: list[str]
    hashtag_categories: dict[str, list]
    best_caption_index: int


# ─── Hashtags ────────────────────────────────────────────────────────────────

class HashtagRecommendRequest(BaseModel):
    caption: str = Field(..., max_length=3000)
    platform: str = Field("instagram", pattern=PLATFORM_PATTERN)
    category: str = Field("lifestyle")
    brand_hashtags: list[str] = Field(default_factory=list)
    languages: list[str] = Field(["fr"])
    exclude_tags: list[str] = Field(default_factory=list)
    n_hashtags: int = Field(25, ge=5, le=30)


class HashtagMetricOut(BaseModel):
    tag: str
    score: float
    reach: float
    engagement_rate: float


class HashtagRecommendOut(BaseModel):
    all_hashtags: list[str]
    categorized: dict[str, list[HashtagMetricOut]]
    estimated_reach: float
    estimated_engagement_rate: float
    banned_detected: list[str]
    rotation_suggestion: list[str]
    performance_score: float


# ─── Timing ──────────────────────────────────────────────────────────────────

class TimingPredictRequest(BaseModel):
    platform: str = Field("instagram", pattern=PLATFORM_PATTERN)
    content_type: str = Field("image")
    account_id: str = ""
    n_slots: int = Field(5, ge=1, le=10)
    is_ramadan: bool = False


class TimingSlotOut(BaseModel):
    day: str
    hour: int
    predicted_engagement_score: float
    confidence: float
    reasoning: str


class TimingPredictOut(BaseModel):
    top_slots: list[TimingSlotOut]
    weekly_heatmap: list[list[float]]
    golden_hours: list[int]
    avoid_hours: list[int]
    timezone: str
    next_optimal: str
    ramadan_adjusted: bool


# ─── Analytics ───────────────────────────────────────────────────────────────

class EngagementPredictRequest(BaseModel):
    platform: str = "instagram"
    content_type: str = "image"
    hour: int = Field(19, ge=0, le=23)
    day_of_week: int = Field(1, ge=0, le=6)
    quality_score: float = Field(75.0, ge=0, le=100)
    hashtag_score: float = Field(70.0, ge=0, le=100)
    caption_length: int = Field(150, ge=0)
    has_face: bool = False
    followers: int = Field(10000, ge=0)


class FactorOut(BaseModel):
    factor: str
    impact: float
    direction: str


class EngagementPredictOut(BaseModel):
    estimated_likes: int
    estimated_comments: int
    estimated_shares: int
    estimated_reach: int
    estimated_engagement_rate: float
    viral_potential: float
    confidence: float
    top_factors: list[FactorOut]


# ─── Comments ────────────────────────────────────────────────────────────────

class CommentAnalyzeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    post_context: str = ""


class CommentBatchRequest(BaseModel):
    texts: list[str] = Field(..., min_length=1, max_length=100)
    baseline_volume: int = Field(100, ge=1)


class CommentAnalysisOut(BaseModel):
    text: str
    language: str
    sentiment: str
    sentiment_score: float
    emotion: str
    is_question: bool
    is_lead: bool
    is_toxic: bool
    is_spam: bool
    reply_priority: str
    urgency_score: int
    entities: dict[str, list[str]]
    topics: list[str]
    suggested_reply: Optional[str]
    auto_hide: bool


class CrisisSignalOut(BaseModel):
    detected: bool
    severity: str
    negative_ratio: float
    volume_spike: float
    dominant_emotion: str
    top_complaints: list[str]
    alert_message: str


class BatchAnalysisOut(BaseModel):
    analyses: list[CommentAnalysisOut]
    crisis: CrisisSignalOut
    summary: dict[str, Any]


# ─── DM Chatbot ──────────────────────────────────────────────────────────────

class DMRespondRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    history: list[dict] = Field(default_factory=list, max_length=20)
    language: str = Field("fr", pattern="^(fr|ar|en)$")
    brand_name: str = Field("Notre Marque", max_length=100)
    brand_knowledge: str = Field("", max_length=3000)
    sender_name: str = Field("Client", max_length=100)


class DMRespondOut(BaseModel):
    message: str
    language: str
    intent: str
    confidence: float
    requires_human: bool
    suggested_actions: list[str]


# ─── Alerts ──────────────────────────────────────────────────────────────────

class AlertOut(BaseModel):
    id: str
    severity: str
    alert_type: str
    title: str
    description: str
    is_acknowledged: bool
    created_at: str
    model_config = {"from_attributes": True}


# ─── Calendar ────────────────────────────────────────────────────────────────

class CalendarEventOut(BaseModel):
    id: str
    platform: str
    account_name: str
    content_type: str
    status: str
    caption_preview: str
    scheduled_at: Optional[float]
    published_at: Optional[float]
    media_urls: list[str]
    hashtags_count: int
    predicted_engagement: Optional[float]
