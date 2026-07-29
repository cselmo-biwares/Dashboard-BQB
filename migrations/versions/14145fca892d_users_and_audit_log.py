"""Add user (editor/analyst accounts) and audit_log tables.

Revision ID: 14145fca892d
Revises: 92000f92ca32
Create Date: 2026-07-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "14145fca892d"
down_revision: Union[str, None] = "92000f92ca32"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the user and audit_log tables."""
    op.create_table(
        "user",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.Enum("editor", "analyst", name="userrole", native_enum=False, length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=10), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_log_action"), "audit_log", ["action"], unique=False)
    op.create_index(op.f("ix_audit_log_created_at"), "audit_log", ["created_at"], unique=False)
    op.create_index(op.f("ix_audit_log_username"), "audit_log", ["username"], unique=False)


def downgrade() -> None:
    """Drop the user and audit_log tables."""
    op.drop_index(op.f("ix_audit_log_username"), table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_created_at"), table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_action"), table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_table("user")
