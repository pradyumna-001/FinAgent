"""backfill_recommendations_from_legacy_tables

Revision ID: 23cd26b9cde6
Revises: 47c0547b9d12
Create Date: 2026-10-29 14:27:17.707541

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '23cd26b9cde6'
down_revision: Union[str, Sequence[str], None] = '47c0547b9d12'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        UPDATE morning_notes mn
        SET recommendations = sub.recs
        FROM (
            SELECT r.morning_note_id,
                   jsonb_build_object(
                       c.ticker, jsonb_build_object(
                           'action', r.action,
                           'confidence', r.confidence,
                           'justification', r.justification,
                           'manager_decision', r.manager_decision,
                           'decided_at', r.decided_at,
                           'decision_channel', r.decision_channel
                       )
                   ) as recs
            FROM recommendations r
            JOIN morning_notes mn2 ON mn2.id = r.morning_note_id
            JOIN companies c ON c.id = mn2.company_id
            WHERE mn2.company_id IS NOT NULL
        ) sub
        WHERE sub.morning_note_id = mn.id
          AND mn.company_id IS NOT NULL;
    """)

def downgrade() -> None:
    op.execute("""
        UPDATE morning_notes
        SET recommendations = '{}'::jsonb
        WHERE company_id IS NOT NULL;
    """)
    