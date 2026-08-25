"""add password_hash to managers

Revision ID: 6f6d0b6496b7
Revises: 7a59dd209592
Create Date: 2026-08-25 17:34:35.139196

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '6f6d0b6496b7'
down_revision: Union[str, Sequence[str], None] = '7a59dd209592'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("managers", sa.Column("password_hash", sa.String(255), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("managers", sa.Column("password_hash"))
    
