"""create finagent_app role and grant DML privileges

Revision ID: 7757cc467c23
Revises: 1700dce69c30
Create Date: 2026-08-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "7757cc467c23"
down_revision: Union[str, Sequence[str], None] = "1700dce69c30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLES = [
    "managers",
    "companies",
    "portfolios",
    "portfolio_holdings",
    "morning_notes",
    "recommendations",
]


def upgrade() -> None:
    # Create the application role with no superuser/bypass privileges
    op.execute(
        "CREATE ROLE finagent_app "
        "NOSUPERUSER NOBYPASSRLS LOGIN"
    )

    # Grant usage on public schema
    op.execute("GRANT USAGE ON SCHEMA public TO finagent_app")

    # Grant DML privileges on all application tables (no DDL, no CREATE)
    for table in TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO finagent_app")

    # Grant usage on sequences for auto-increment columns
    op.execute("GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO finagent_app")


def downgrade() -> None:
    # Revoke all privileges before dropping the role
    for table in TABLES:
        op.execute(f"REVOKE ALL ON {table} FROM finagent_app")

    op.execute("REVOKE USAGE ON ALL SEQUENCES IN SCHEMA public FROM finagent_app")
    op.execute("REVOKE USAGE ON SCHEMA public FROM finagent_app")

    # Drop the role
    op.execute("DROP ROLE IF EXISTS finagent_app")