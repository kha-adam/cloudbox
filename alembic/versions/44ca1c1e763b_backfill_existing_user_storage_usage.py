"""Backfill existing user storage usage

Revision ID: 44ca1c1e763b
Revises: 1de3d1325c3e
Create Date: 2026-10-13 10:51:43.954291

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '44ca1c1e763b'
down_revision: Union[str, Sequence[str], None] = '1de3d1325c3e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        UPDATE users
        SET storage_used = COALESCE(
            (
                SELECT SUM(files.size)
                FROM files
                WHERE files.owner_id = users.id
            ),
            0
        )
    """)


def downgrade() -> None:
    pass
