"""Add prompt_override table for front-configurable LLM system prompts.

Revision ID: 92000f92ca32
Revises: fd4c6d1ab493
Create Date: 2026-07-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "92000f92ca32"
down_revision: Union[str, None] = "fd4c6d1ab493"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the prompt_override table."""
    op.create_table(
        "prompt_override",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    """Drop the prompt_override table."""
    op.drop_table("prompt_override")
