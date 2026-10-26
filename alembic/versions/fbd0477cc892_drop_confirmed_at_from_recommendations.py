"""drop confirmed_at from recommendations

Revision ID: fbd0477cc892
Revises: deac72d69cdc
Create Date: 2026-10-26 16:31:39.622285

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'fbd0477cc892'
down_revision: Union[str, Sequence[str], None] = 'deac72d69cdc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column("recommendations", "confirmed_at")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        "recommendations",
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
