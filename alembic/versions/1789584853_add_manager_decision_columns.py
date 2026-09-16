"""add manager decision columns to recommendations

Revision ID: 1789584853
Revises: 1787160772_add_hnsw_reindex_state_table.py
Create Date: 2026-09-16 16:30:53.714239200

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '1789584853'
down_revision: Union[str, Sequence[str], None] = '1787160772'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("recommendations", sa.Column("manager_decision", sa.String(16), nullable=False, server_default=sa.text("'pending'")))
    op.add_column("recommendations", sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("recommendations", sa.Column("decision_channel", sa.Text(), nullable=True))
    op.add_column("recommendations", sa.Column("telegram_update_id", sa.BigInteger(), nullable=True, unique=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("recommendations", "telegram_update_id")
    op.drop_column("recommendations", "decision_channel")
    op.drop_column("recommendations", "decided_at")
    op.drop_column("recommendations", "manager_decision")