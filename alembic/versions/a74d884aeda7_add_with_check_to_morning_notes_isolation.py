"""add WITH CHECK to morning_notes_manager_isolation policy

Revision ID: a74d884aeda7
Revises: 1700dce69c30
Create Date: 2026-08-07 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "a74d884aeda7"
down_revision: Union[str, Sequence[str], None] = "1700dce69c30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER POLICY morning_notes_manager_isolation ON morning_notes "
        "WITH CHECK (manager_id = current_setting('app.manager_id', true)::int)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER POLICY morning_notes_manager_isolation ON morning_notes "
        "USING (manager_id = current_setting('app.manager_id', true)::int)"
    )
