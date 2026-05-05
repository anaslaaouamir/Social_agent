"""Initial migration — create all tables.

Revision ID: 0001_initial
Revises:
Create Date: 2025-01-01 00:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("preferred_language", sa.String(5), nullable=False, server_default="fr"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # social_accounts
    op.create_table(
        "social_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("account_id", sa.String(255), nullable=False),
        sa.Column("account_name", sa.String(255), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.Float(), nullable=True),
        sa.Column("followers_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("platform", "account_id", name="uq_platform_account"),
    )
    op.create_index("ix_social_account_user", "social_accounts", ["user_id"])

    # posts
    op.create_table(
        "posts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("hashtags", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("media_urls", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("scheduled_at", sa.Float(), nullable=True),
        sa.Column("published_at", sa.Float(), nullable=True),
        sa.Column("platform_post_id", sa.String(255), nullable=True),
        sa.Column("ai_caption_variants", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("ai_hashtag_suggestions", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("ai_quality_score", sa.Float(), nullable=True),
        sa.Column("ai_predicted_engagement", sa.Float(), nullable=True),
        sa.Column("visual_analysis", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("likes_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("comments_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("shares_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reach", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("impressions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("engagement_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["account_id"], ["social_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_post_status_scheduled", "posts", ["status", "scheduled_at"])
    op.create_index("ix_post_account", "posts", ["account_id"])

    # comments
    op.create_table(
        "comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("post_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("platform_comment_id", sa.String(255), nullable=False),
        sa.Column("author_id", sa.String(255), nullable=False),
        sa.Column("author_name", sa.String(255), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("sentiment", sa.String(50), nullable=True),
        sa.Column("sentiment_score", sa.Float(), nullable=True),
        sa.Column("emotion", sa.String(50), nullable=True),
        sa.Column("is_question", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_lead", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("reply_priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("auto_replied", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("auto_reply_text", sa.Text(), nullable=True),
        sa.Column("is_hidden", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("nlp_entities", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("platform_comment_id"),
    )
    op.create_index("ix_comment_post_sentiment", "comments", ["post_id", "sentiment"])
    op.create_index("ix_comment_priority", "comments", ["reply_priority"])

    # direct_messages
    op.create_table(
        "direct_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sender_id", sa.String(255), nullable=False),
        sa.Column("sender_name", sa.String(255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("language_detected", sa.String(10), nullable=False, server_default="fr"),
        sa.Column("ai_response", sa.Text(), nullable=True),
        sa.Column("conversation_history", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("intent", sa.String(100), nullable=True),
        sa.Column("sentiment_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("is_resolved", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("human_handoff", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["account_id"], ["social_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # hashtag_performance
    op.create_table(
        "hashtag_performance",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("hashtag", sa.String(255), nullable=False),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("avg_reach", sa.Float(), nullable=False, server_default="0"),
        sa.Column("avg_engagement_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("trending_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("post_count_24h", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_banned", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_niche", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("market", sa.String(10), nullable=False, server_default="MA"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("hashtag", "platform", "market", name="uq_hashtag_platform_market"),
    )
    op.create_index("ix_hashtag_performance_hashtag", "hashtag_performance", ["hashtag"])

    # alerts
    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("severity", sa.String(50), nullable=False),
        sa.Column("alert_type", sa.String(100), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("is_acknowledged", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("acknowledged_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["account_id"], ["social_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alert_severity_ack", "alerts", ["severity", "is_acknowledged"])

    # account_metrics
    op.create_table(
        "account_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("timestamp", sa.Float(), nullable=False),
        sa.Column("followers_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("following_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("posts_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_engagement_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("reach_24h", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("impressions_24h", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_followers_24h", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("profile_visits_24h", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["account_id"], ["social_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_metric_account_ts", "account_metrics", ["account_id", "timestamp"])


def downgrade() -> None:
    op.drop_table("account_metrics")
    op.drop_table("alerts")
    op.drop_table("hashtag_performance")
    op.drop_table("direct_messages")
    op.drop_table("comments")
    op.drop_table("posts")
    op.drop_table("social_accounts")
    op.drop_table("users")
