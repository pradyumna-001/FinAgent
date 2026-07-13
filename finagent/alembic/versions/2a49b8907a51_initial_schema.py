"""initial_schema

Revision ID: 2a49b8907a51
Revises: 
Create Date: 2026-07-13 15:53:32.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import pgvector

# revision identifiers, used by Alembic.
revision: str = '2a49b8907a51'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Manually ensure the pgvector extension is initialized
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # 2. Execute auto-generated structural schema tables
    op.create_table(
        'companies',
        sa.Column('company_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('ticker', sa.String(length=12), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('sector', sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint('company_id'),
        sa.UniqueConstraint('ticker')
    )
    
    op.create_table(
        'managers',
        sa.Column('manager_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint('manager_id'),
        sa.UniqueConstraint('email')
    )
    
    op.create_table(
        'portfolios',
        sa.Column('manager_id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.company_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['manager_id'], ['managers.manager_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('manager_id', 'company_id')
    )
    
    op.create_table(
        'morning_notes',
        sa.Column('morning_note_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('pipeline_run_id', sa.String(length=64), nullable=False),
        sa.Column('manager_id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.DateTime(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('confidence_score', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('data_freshness', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('flags', postgresql.ARRAY(postgresql.JSONB(astext_type=sa.Text())), nullable=True),
        sa.Column('status', sa.Enum('pending', 'generating', 'completed', 'failed', name='status_enum'), nullable=False),
        sa.Column('embedding', pgvector.sqlalchemy.Vector(dim=1536), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.company_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['manager_id'], ['managers.manager_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('morning_note_id')
    )
    
    # Core performance tuning indexes updated to use postgresql_where
    op.create_index('idx_manager_company_data', 'morning_notes', ['manager_id', 'company_id', 'date'], unique=False)
    op.create_index(
        'idx_partial_completed_data', 
        'morning_notes', 
        ['date'], 
        unique=False, 
        postgresql_where=sa.text("status = 'completed'")
    )
    
    op.create_table(
        'recommendations',
        sa.Column('recommendation_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('morning_note_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(length=20), nullable=False),
        sa.Column('justification', sa.Text(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(['morning_note_id'], ['morning_notes.morning_note_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('recommendation_id')
    )

    # 3. Apply Multi-Tenant Row Level Security (RLS) policies
    op.execute("ALTER TABLE morning_notes ENABLE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY manager_isolation_policy ON morning_notes
        USING (manager_id = NULLIF(current_setting('app.current_manager_id', True), '')::integer);
    """)


def downgrade() -> None:
    # Safely strip out the structural rules and extensions in exact reverse order
    op.execute("DROP POLICY IF EXISTS manager_isolation_policy ON morning_notes;")
    op.execute("ALTER TABLE morning_notes DISABLE ROW LEVEL SECURITY;")
    
    op.drop_table('recommendations')
    op.drop_index('idx_partial_completed_data', table_name='morning_notes')
    op.drop_index('idx_manager_company_data', table_name='morning_notes')
    op.drop_table('morning_notes')
    op.drop_table('portfolios')
    op.drop_table('managers')
    op.drop_table('companies')
    
    # Safely drop the type registry profile cleanups
    op.execute("DROP TYPE IF EXISTS status_enum;")
    op.execute("DROP EXTENSION IF EXISTS vector;")