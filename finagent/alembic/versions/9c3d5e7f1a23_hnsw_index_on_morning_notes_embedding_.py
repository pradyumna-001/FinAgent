"""hnsw index on morning_notes.embedding

Revision ID: 9c3d5e7f1a23
Revises: 8b2c4d6e9f01
Create Date: 2026-07-28 19:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import HALFVEC, Vector


revision: str = "9c3d5e7f1a23"
down_revision: Union[str, Sequence[str], None] = "8b2c4d6e9f01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("morning_notes", "embedding")
    op.add_column(
        "morning_notes",
        sa.Column("embedding", HALFVEC(2048), nullable=True),
    )
    op.execute(
        "CREATE INDEX idx_morning_notes_embedding_hnsw "
        "ON morning_notes USING hnsw (embedding halfvec_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_morning_notes_embedding_hnsw")
    op.drop_column("morning_notes", "embedding")
    op.add_column(
        "morning_notes",
        sa.Column("embedding", Vector(2048), nullable=True),
    )
