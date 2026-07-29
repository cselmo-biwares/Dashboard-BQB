"""Store all timestamps as TIMESTAMPTZ instead of naive TIMESTAMP.

The app always works with timezone-aware UTC datetimes (Conversation Manager
responses, `datetime.now(timezone.utc)`), which asyncpg refuses to bind against a
TIMESTAMP WITHOUT TIME ZONE column ("can't subtract offset-naive and offset-aware
datetimes").

Revision ID: fd4c6d1ab493
Revises: b4351a8aac09
Create Date: 2026-07-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fd4c6d1ab493"
down_revision: Union[str, None] = "b4351a8aac09"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = [
    ("topic", "created_at"),
    ("document", "created_at"),
    ("document", "updated_at"),
    ("topic_document", "created_at"),
    ("conversation_topic", "created_at"),
    ("processed_conversation", "source_created_at"),
    ("processed_conversation", "processed_at"),
    ("ingestion_run", "started_at"),
    ("ingestion_run", "finished_at"),
]


def upgrade() -> None:
    """Convert all timestamp columns to TIMESTAMPTZ, assuming existing naive values are UTC."""
    for table, column in _COLUMNS:
        op.alter_column(
            table,
            column,
            type_=sa.DateTime(timezone=True),
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )


def downgrade() -> None:
    """Convert all timestamp columns back to naive TIMESTAMP (UTC wall-clock)."""
    for table, column in _COLUMNS:
        op.alter_column(
            table,
            column,
            type_=sa.DateTime(timezone=False),
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )
