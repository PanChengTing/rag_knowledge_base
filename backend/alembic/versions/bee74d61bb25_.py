"""empty message

Revision ID: bee74d61bb25
Revises: ac3b19991533
Create Date: 2026-09-08 13:36:45.969862

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bee74d61bb25'
down_revision: Union[str, Sequence[str], None] = 'ac3b19991533'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
