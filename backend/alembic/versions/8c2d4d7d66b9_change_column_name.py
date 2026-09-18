"""change column name

Revision ID: 8c2d4d7d66b9
Revises: ffb03865b2d7
Create Date: 2026-09-18 12:33:56.416383

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8c2d4d7d66b9'
down_revision: Union[str, Sequence[str], None] = 'ffb03865b2d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "roles",
        "descripition",
        new_column_name="description",
        existing_type=sa.String(length=256),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "roles",
        "description",
        new_column_name="descripition",
        existing_type=sa.String(length=256),
        existing_nullable=False,
    )
    # ### end Alembic commands ###
