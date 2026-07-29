"""Add analyst_note table.

Revision ID: 7a3f9c2e1b4d
Revises: 14145fca892d
Create Date: 2026-07-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7a3f9c2e1b4d"
down_revision: Union[str, None] = "14145fca892d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the analyst_note table."""
    op.create_table(
        "analyst_note",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("topic_id", sa.Integer(), nullable=True),
        sa.Column("leaf_path", sa.String(length=500), nullable=True),
        sa.Column("resolution", sa.String(length=12), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("updated_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["topic_id"], ["topic.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_analyst_note_topic_id"), "analyst_note", ["topic_id"], unique=False)


def downgrade() -> None:
    """Drop the analyst_note table."""
    op.drop_index(op.f("ix_analyst_note_topic_id"), table_name="analyst_note")
    op.drop_table("analyst_note")
