"""add hnsw_reindex_state table for tracking reindex operations

Revision ID: add_hnsw_reindex_state
Revises: a74d884aeda7
Create Date: 2026-08-19 14:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "add_hnsw_reindex_state"
down_revision: Union[str, Sequence[str], None] = "a74d884aeda7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "hnsw_reindex_state",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("index_name", sa.String(length=128), nullable=False, unique=True),
        sa.Column("last_reindex_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_reindex_duration_ms", sa.Integer(), nullable=True),
        sa.Column("last_reindex_rows", sa.BigInteger(), nullable=True),
        sa.Column("last_reindex_idx_scan", sa.BigInteger(), nullable=True),
        sa.Column("last_reindex_tuples_read", sa.BigInteger(), nullable=True),
        sa.Column("last_reindex_status", sa.String(length=16), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("next_scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("config", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_hnsw_reindex_state_index_name", "hnsw_reindex_state", ["index_name"])


def downgrade() -> None:
    op.drop_index("ix_hnsw_reindex_state_index_name", table_name="hnsw_reindex_state")
    op.drop_table("hnsw_reindex_state")
