"""empty message

Revision ID: fdfba1dc8d26
Revises: bee74d61bb25
Create Date: 2026-09-08 13:37:31.068003

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fdfba1dc8d26'
down_revision: Union[str, Sequence[str], None] = 'bee74d61bb25'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
