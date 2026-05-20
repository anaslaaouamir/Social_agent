"""Domain models for the social agent platform."""
import uuid
import enum
from typing import Optional
from datetime import datetime, timezone
from sqlalchemy import (
    String, Text, Float, Integer, Boolean, Enum,
    ForeignKey, JSON, Index, UniqueConstraint, DateTime, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator, CHAR
from sqlalchemy.dialects.postgresql import UUID, JSONB
from core.database import Base


class GUID(TypeDecorator):
    """UUID type that works on both PostgreSQL and SQLite."""

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        return str(value if isinstance(value, uuid.UUID) else uuid.UUID(str(value)))

    def process_result_value(self, value, dialect):
        if value is None or isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


JSON_VARIANT = JSON().with_variant(JSONB, "postgresql")


class Platform(str, enum.Enum):
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    LINKEDIN = "linkedin"
    FACEBOOK = "facebook"
    TWITTER = "twitter"
    THREADS = "threads"
    YOUTUBE = "youtube"
    PINTEREST = "pinterest"


class PostStatus(str, enum.Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ContentType(str, enum.Enum):
    IMAGE = "image"
    VIDEO = "video"
    CAROUSEL = "carousel"
    REEL = "reel"
    STORY = "story"


class SentimentLabel(str, enum.Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    SPAM = "spam"
    TOXIC = "toxic"


class AlertSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    preferred_language: Mapped[str] = mapped_column(String(5), default="fr")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    accounts: Mapped[list["SocialAccount"]] = relationship(back_populates="user", lazy="selectin")


class SocialAccount(Base):
    __tablename__ = "social_accounts"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id"), nullable=False)
    platform: Mapped[Platform] = mapped_column(Enum(Platform), nullable=False)
    account_id: Mapped[str] = mapped_column(String(255), nullable=False)
    account_name: Mapped[str] = mapped_column(String(255), nullable=False)
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    followers_count: Mapped[int] = mapped_column(Integer, default=0)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON_VARIANT, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="accounts")
    posts: Mapped[list["Post"]] = relationship(back_populates="account")
    metrics: Mapped[list["AccountMetric"]] = relationship(back_populates="account")

    __table_args__ = (
        UniqueConstraint("platform", "account_id", name="uq_platform_account"),
        Index("ix_social_account_user", "user_id"),
    )


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("social_accounts.id"), nullable=False)
    content_type: Mapped[ContentType] = mapped_column(Enum(ContentType), nullable=False)
    status: Mapped[PostStatus] = mapped_column(Enum(PostStatus), default=PostStatus.DRAFT, nullable=False)
    caption: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    hashtags: Mapped[list] = mapped_column(JSON_VARIANT, default=list)
    media_urls: Mapped[list] = mapped_column(JSON_VARIANT, default=list)
    scheduled_at: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    published_at: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    platform_post_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # AI-generated metadata
    ai_caption_variants: Mapped[list] = mapped_column(JSON_VARIANT, default=list)
    ai_hashtag_suggestions: Mapped[list] = mapped_column(JSON_VARIANT, default=list)
    ai_quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ai_predicted_engagement: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    visual_analysis: Mapped[dict] = mapped_column(JSON_VARIANT, default=dict)

    # Performance (filled after publishing)
    likes_count: Mapped[int] = mapped_column(Integer, default=0)
    comments_count: Mapped[int] = mapped_column(Integer, default=0)
    shares_count: Mapped[int] = mapped_column(Integer, default=0)
    reach: Mapped[int] = mapped_column(Integer, default=0)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    engagement_rate: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    account: Mapped["SocialAccount"] = relationship(back_populates="posts")
    comments: Mapped[list["Comment"]] = relationship(back_populates="post")

    __table_args__ = (
        Index("ix_post_status_scheduled", "status", "scheduled_at"),
        Index("ix_post_account", "account_id"),
    )


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    post_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("posts.id"), nullable=False)
    platform_comment_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    author_id: Mapped[str] = mapped_column(String(255), nullable=False)
    author_name: Mapped[str] = mapped_column(String(255), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    sentiment: Mapped[Optional[SentimentLabel]] = mapped_column(Enum(SentimentLabel), nullable=True)
    sentiment_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    emotion: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    is_question: Mapped[bool] = mapped_column(Boolean, default=False)
    is_lead: Mapped[bool] = mapped_column(Boolean, default=False)
    reply_priority: Mapped[int] = mapped_column(Integer, default=0)
    auto_replied: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_reply_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    nlp_entities: Mapped[dict] = mapped_column(JSON_VARIANT, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    post: Mapped["Post"] = relationship(back_populates="comments")

    __table_args__ = (
        Index("ix_comment_post_sentiment", "post_id", "sentiment"),
        Index("ix_comment_priority", "reply_priority"),
    )


class DirectMessage(Base):
    __tablename__ = "direct_messages"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("social_accounts.id"), nullable=False)
    sender_id: Mapped[str] = mapped_column(String(255), nullable=False)
    sender_name: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    language_detected: Mapped[str] = mapped_column(String(10), default="fr")
    ai_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    conversation_history: Mapped[list] = mapped_column(JSON_VARIANT, default=list)
    intent: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    sentiment_score: Mapped[float] = mapped_column(Float, default=0.0)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    human_handoff: Mapped[bool] = mapped_column(Boolean, default=False)


class LLMMemoryEntry(Base):
    __tablename__ = "llm_memory_entries"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id"), nullable=False)
    session_id: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    feature: Mapped[str] = mapped_column(String(100), default="general", nullable=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON_VARIANT, default=dict)

    __table_args__ = (
        Index("ix_llm_memory_user_session_created", "user_id", "session_id", "created_at"),
        Index("ix_llm_memory_feature", "feature"),
    )


class HashtagPerformance(Base):
    __tablename__ = "hashtag_performance"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    hashtag: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    platform: Mapped[Platform] = mapped_column(Enum(Platform), nullable=False)
    avg_reach: Mapped[float] = mapped_column(Float, default=0.0)
    avg_engagement_rate: Mapped[float] = mapped_column(Float, default=0.0)
    trending_score: Mapped[float] = mapped_column(Float, default=0.0)
    post_count_24h: Mapped[int] = mapped_column(Integer, default=0)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    is_niche: Mapped[bool] = mapped_column(Boolean, default=False)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    market: Mapped[str] = mapped_column(String(10), default="MA")

    __table_args__ = (
        UniqueConstraint("hashtag", "platform", "market", name="uq_hashtag_platform_market"),
    )


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("social_accounts.id"), nullable=False)
    severity: Mapped[AlertSeverity] = mapped_column(Enum(AlertSeverity), nullable=False)
    alert_type: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON_VARIANT, default=dict)
    is_acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    acknowledged_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_alert_severity_ack", "severity", "is_acknowledged"),
    )


class AccountMetric(Base):
    __tablename__ = "account_metrics"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("social_accounts.id"), nullable=False)
    timestamp: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    followers_count: Mapped[int] = mapped_column(Integer, default=0)
    following_count: Mapped[int] = mapped_column(Integer, default=0)
    posts_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_engagement_rate: Mapped[float] = mapped_column(Float, default=0.0)
    reach_24h: Mapped[int] = mapped_column(Integer, default=0)
    impressions_24h: Mapped[int] = mapped_column(Integer, default=0)
    new_followers_24h: Mapped[int] = mapped_column(Integer, default=0)
    profile_visits_24h: Mapped[int] = mapped_column(Integer, default=0)

    account: Mapped["SocialAccount"] = relationship(back_populates="metrics")

    __table_args__ = (
        Index("ix_metric_account_ts", "account_id", "timestamp"),
    )
