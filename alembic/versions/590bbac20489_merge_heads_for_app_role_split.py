"""merge heads for app role split

Revision ID: 590bbac20489
Revises: 7757cc467c23, a74d884aeda7
Create Date: 2026-08-19 14:05:44.676851

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = '590bbac20489'
down_revision: Union[str, Sequence[str], None] = ('7757cc467c23', 'a74d884aeda7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
