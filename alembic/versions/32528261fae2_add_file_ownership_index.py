"""Add file ownership index

Revision ID: 32528261fae2
Revises: 554e91820c2a
Create Date: 2026-10-08 13:40:36.120178

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '32528261fae2'
down_revision: Union[str, Sequence[str], None] = '554e91820c2a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
            CREATE INDEX idx_files_owner_created_id
            ON files (owner_id, created_at DESC, id DESC)
        """
    )


def downgrade() -> None:
    op.execute(
        """
            DROP INDEX idx_files_owner_created_id
        """
    )