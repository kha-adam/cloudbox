"""Make file ownership required

Revision ID: e3948ec3f121
Revises: 32528261fae2
Create Date: 2026-10-08 14:10:27.994904

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e3948ec3f121"
down_revision: str | Sequence[str] | None = "32528261fae2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "files",
        "owner_id",
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "files",
        "owner_id",
        nullable=False,
    )
