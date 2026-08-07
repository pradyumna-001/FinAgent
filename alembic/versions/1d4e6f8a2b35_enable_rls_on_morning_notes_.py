"""enable RLS on morning_notes by manager_id

Revision ID: 1d4e6f8a2b35
Revises: 9c3d5e7f1a23
Create Date: 2026-07-28 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "1d4e6f8a2b35"
down_revision: Union[str, Sequence[str], None] = "9c3d5e7f1a23"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE morning_notes ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY morning_notes_manager_isolation "
        "ON morning_notes "
        "USING (manager_id = current_setting('app.manager_id', true)::int) "
        "WITH CHECK (manager_id = current_setting('app.manager_id', true)::int)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS morning_notes_manager_isolation ON morning_notes")
    op.execute("ALTER TABLE morning_notes DISABLE ROW LEVEL SECURITY")
