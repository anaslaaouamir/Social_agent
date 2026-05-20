"""Add durable LLM memory entries.

Revision ID: 0004_add_llm_memory_entries
Revises: 0003_add_threads_platform
Create Date: 2026-05-13 18:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_add_llm_memory_entries"
down_revision = "0003_add_threads_platform"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_memory_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("feature", sa.String(100), nullable=False, server_default="general"),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_llm_memory_user_session_created",
        "llm_memory_entries",
        ["user_id", "session_id", "created_at"],
    )
    op.create_index("ix_llm_memory_feature", "llm_memory_entries", ["feature"])


def downgrade() -> None:
    op.drop_index("ix_llm_memory_feature", table_name="llm_memory_entries")
    op.drop_index("ix_llm_memory_user_session_created", table_name="llm_memory_entries")
    op.drop_table("llm_memory_entries")
