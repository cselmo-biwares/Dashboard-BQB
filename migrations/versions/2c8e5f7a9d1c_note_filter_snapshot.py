"""Add filter snapshot columns to analyst_note.

Revision ID: 2c8e5f7a9d1c
Revises: 7a3f9c2e1b4d
Create Date: 2026-07-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2c8e5f7a9d1c"
down_revision: Union[str, None] = "7a3f9c2e1b4d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add filter_source/filter_from/filter_to columns to analyst_note."""
    op.add_column("analyst_note", sa.Column("filter_source", sa.String(length=64), nullable=True))
    op.add_column("analyst_note", sa.Column("filter_from", sa.DateTime(timezone=True), nullable=True))
    op.add_column("analyst_note", sa.Column("filter_to", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Drop the filter snapshot columns."""
    op.drop_column("analyst_note", "filter_to")
    op.drop_column("analyst_note", "filter_from")
    op.drop_column("analyst_note", "filter_source")
