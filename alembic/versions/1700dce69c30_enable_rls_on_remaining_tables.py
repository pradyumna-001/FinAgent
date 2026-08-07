"""enable RLS on managers, companies, portfolios, portfolio_holdings, recommendations

Revision ID: 1700dce69c30
Revises: 1d4e6f8a2b35
Create Date: 2026-08-06 18:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "1700dce69c30"
down_revision: Union[str, Sequence[str], None] = "1d4e6f8a2b35"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE managers ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY managers_all_visible "
        "ON managers "
        "FOR ALL "
        "USING (true) "
        "WITH CHECK (true)"
    )

    op.execute("ALTER TABLE companies ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY companies_all_visible "
        "ON companies "
        "FOR ALL "
        "USING (true) "
        "WITH CHECK (true)"
    )

    op.execute("ALTER TABLE portfolios ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY portfolios_manager_isolation "
        "ON portfolios "
        "USING (manager_id = current_setting('app.manager_id', true)::int) "
        "WITH CHECK (manager_id = current_setting('app.manager_id', true)::int)"
    )

    op.execute("ALTER TABLE portfolio_holdings ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY portfolio_holdings_via_portfolio "
        "ON portfolio_holdings "
        "USING (EXISTS ("
        "  SELECT 1 FROM portfolios p "
        "  WHERE p.id = portfolio_holdings.portfolio_id "
        "  AND p.manager_id = current_setting('app.manager_id', true)::int"
        "))"
        "WITH CHECK  (EXISTS ("
                "  SELECT 1 FROM portfolios p "
                "  WHERE p.id = portfolio_holdings.portfolio_id "
                "  AND p.manager_id = current_setting('app.manager_id', true)::int"
        "))"
    )

    op.execute("ALTER TABLE recommendations ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY recommendations_via_morning_note "
        "ON recommendations "
        "USING (EXISTS ("
        "  SELECT 1 FROM morning_notes mn "
        "  WHERE mn.id = recommendations.morning_note_id "
        "  AND mn.manager_id = current_setting('app.manager_id', true)::int"
        ")) "
        "WITH CHECK (EXISTS ("
                "  SELECT 1 FROM morning_notes mn "
                "  WHERE mn.id = recommendations.morning_note_id "
                "  AND mn.manager_id = current_setting('app.manager_id', true)::int"
        "))"
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS recommendations_via_morning_note ON recommendations"
    )
    op.execute("ALTER TABLE recommendations DISABLE ROW LEVEL SECURITY")

    op.execute(
        "DROP POLICY IF EXISTS portfolio_holdings_via_portfolio ON portfolio_holdings"
    )
    op.execute("ALTER TABLE portfolio_holdings DISABLE ROW LEVEL SECURITY")

    op.execute("DROP POLICY IF EXISTS portfolios_manager_isolation ON portfolios")
    op.execute("ALTER TABLE portfolios DISABLE ROW LEVEL SECURITY")

    op.execute("DROP POLICY IF EXISTS companies_all_visible ON companies")
    op.execute("ALTER TABLE companies DISABLE ROW LEVEL SECURITY")

    op.execute("DROP POLICY IF EXISTS managers_all_visible ON managers")
    op.execute("ALTER TABLE managers DISABLE ROW LEVEL SECURITY")
