"""initial schema with five tables and status check

Revision ID: 5d03259528be
Revises:
Create Date: 2026-07-27 19:04:47.722958

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from app.db.models import MorningNoteStatus


# revision identifiers, used by Alembic.
revision: str = "5d03259528be"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


STATUS_VALUES = ", ".join(repr(s.value) for s in MorningNoteStatus)


def upgrade() -> None:
    op.create_table(
        "managers",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("ticker", sa.String(length=12), nullable=False, unique=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("sector", sa.String(length=120), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "portfolios",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "manager_id",
            sa.Integer(),
            sa.ForeignKey("managers.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_portfolios_manager_id", "portfolios", ["manager_id"])

    op.create_table(
        "portfolio_holdings",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "portfolio_id",
            sa.Integer(),
            sa.ForeignKey("portfolios.id"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id"),
            nullable=False,
        ),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_portfolio_holdings_portfolio_id", "portfolio_holdings", ["portfolio_id"]
    )
    op.create_index(
        "ix_portfolio_holdings_company_id", "portfolio_holdings", ["company_id"]
    )

    op.create_table(
        "morning_notes",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "portfolio_id",
            sa.Integer(),
            sa.ForeignKey("portfolios.id"),
            nullable=False,
        ),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("note_text", sa.Text(), nullable=False),
        sa.Column("pipeline_run_id", sa.String(length=64), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            sa.CheckConstraint(
                f"status IN ({STATUS_VALUES})", name="ck_morning_notes_status"
            ),
            server_default=MorningNoteStatus.PENDING.value,
            nullable=False,
        ),
        sa.Column(
            "confidence_scores",
            JSONB,
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "data_freshness",
            JSONB,
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "flags",
            JSONB,
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "manager_id",
            sa.Integer(),
            sa.ForeignKey("managers.id"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id"),
            nullable=False,
        ),
    )
    op.create_index("ix_morning_notes_portfolio_id", "morning_notes", ["portfolio_id"])
    op.create_index("ix_morning_notes_manager_id", "morning_notes", ["manager_id"])
    op.create_index("ix_morning_notes_company_id", "morning_notes", ["company_id"])
    op.create_index(
        "ix_morning_notes_pipeline_run_id", "morning_notes", ["pipeline_run_id"]
    )

    op.create_table(
        "recommendations",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "morning_note_id",
            sa.Integer(),
            sa.ForeignKey("morning_notes.id"),
            nullable=False,
        ),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_recommendations_morning_note_id", "recommendations", ["morning_note_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_recommendations_morning_note_id", table_name="recommendations")
    op.drop_table("recommendations")

    op.drop_index("ix_morning_notes_pipeline_run_id", table_name="morning_notes")
    op.drop_index("ix_morning_notes_company_id", table_name="morning_notes")
    op.drop_index("ix_morning_notes_manager_id", table_name="morning_notes")
    op.drop_index("ix_morning_notes_portfolio_id", table_name="morning_notes")
    op.drop_table("morning_notes")

    op.drop_index(
        "ix_portfolio_holdings_company_id", table_name="portfolio_holdings"
    )
    op.drop_index(
        "ix_portfolio_holdings_portfolio_id", table_name="portfolio_holdings"
    )
    op.drop_table("portfolio_holdings")

    op.drop_index("ix_portfolios_manager_id", table_name="portfolios")
    op.drop_table("portfolios")

    op.drop_table("companies")
    op.drop_table("managers")