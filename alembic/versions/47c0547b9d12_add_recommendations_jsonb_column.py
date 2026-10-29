"""add_recommendations_jsonb_column

Revision ID: 47c0547b9d12
Revises: fbd0477cc892
Create Date: 2026-10-29 14:14:06.216580

"""
from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '47c0547b9d12'
down_revision: Union[str, None] = 'fbd0477cc892'
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "morning_notes",
        sa.Column("recommendations", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("morning_notes", "recommendations")
