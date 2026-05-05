"""Add timestamps to all tables.

Revision ID: 0002_add_timestamps
Revises: 0001_initial
Create Date: 2026-01-01 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_add_timestamps"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add created_at / updated_at to tables that are missing them
    # (migration 0001 already adds them to users and social_accounts)
    for table in ("posts", "comments", "direct_messages", "alerts", "account_metrics", "hashtag_performance"):
        try:
            op.add_column(
                table,
                sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            )
        except Exception:
            pass  # column already exists

    for table in ("posts", "direct_messages"):
        try:
            op.add_column(
                table,
                sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            )
        except Exception:
            pass


def downgrade() -> None:
    for table in ("posts", "comments", "direct_messages", "alerts", "account_metrics", "hashtag_performance"):
        try:
            op.drop_column(table, "created_at")
        except Exception:
            pass
    for table in ("posts", "direct_messages"):
        try:
            op.drop_column(table, "updated_at")
        except Exception:
            pass
