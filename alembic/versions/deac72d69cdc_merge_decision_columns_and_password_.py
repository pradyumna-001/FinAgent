"""merge decision columns and password hash heads

Revision ID: deac72d69cdc
Revises: 1789584853, 6f6d0b6496b7
Create Date: 2026-09-23 17:42:17.939965

"""
from typing import Sequence, Union



# revision identifiers, used by Alembic.
revision: str = 'deac72d69cdc'
down_revision: Union[str, Sequence[str], None] = ('1789584853', '6f6d0b6496b7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
