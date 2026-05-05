"""Add new social platforms to platform enum.

Revision ID: 0003_add_threads_platform
Revises: 0002_add_timestamps
Create Date: 2026-05-04 15:00:00
"""
from alembic import op

revision = "0003_add_threads_platform"
down_revision = "0002_add_timestamps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE platform ADD VALUE IF NOT EXISTS 'THREADS'")
    op.execute("ALTER TYPE platform ADD VALUE IF NOT EXISTS 'YOUTUBE'")
    op.execute("ALTER TYPE platform ADD VALUE IF NOT EXISTS 'PINTEREST'")


def downgrade() -> None:
    # PostgreSQL does not support dropping enum values directly.
    pass
