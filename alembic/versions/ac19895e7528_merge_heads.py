"""merge_heads

Revision ID: ac19895e7528
Revises: add_hnsw_reindex_state, 590bbac20489
Create Date: 2026-08-20 18:49:16.399321

"""
from typing import Sequence, Union



# revision identifiers, used by Alembic.
revision: str = 'ac19895e7528'
down_revision: Union[str, Sequence[str], None] = ('add_hnsw_reindex_state', '590bbac20489')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
