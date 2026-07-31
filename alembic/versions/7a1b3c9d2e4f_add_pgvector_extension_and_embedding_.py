"""add pgvector extension and embedding column

Revision ID: 7a1b3c9d2e4f
Revises: 5d03259528be
Create Date: 2026-07-28 18:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision: str = "7a1b3c9d2e4f"
down_revision: Union[str, Sequence[str], None] = "5d03259528be"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column(
        "morning_notes",
        sa.Column("embedding", Vector(2048), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("morning_notes", "embedding")


