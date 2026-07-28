"""composite and partial indexes on morning_notes

Revision ID: 8b2c4d6e9f01
Revises: 7a1b3c9d2e4f
Create Date: 2026-07-28 19:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "8b2c4d6e9f01"
down_revision: Union[str, Sequence[str], None] = "7a1b3c9d2e4f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_morning_notes_manager_company_date",
        "morning_notes",
        ["manager_id", "company_id", "generated_at"],
    )
    op.create_index(
        "idx_morning_notes_completed_at",
        "morning_notes",
        ["generated_at"],
        postgresql_where=sa.text("status = 'completed'")
    )


def downgrade() -> None:
    op.drop_index("idx_morning_notes_completed_at", table_name="morning_notes")
    op.drop_index("ix_morning_notes_manager_company_date", table_name="morning_notes")
    