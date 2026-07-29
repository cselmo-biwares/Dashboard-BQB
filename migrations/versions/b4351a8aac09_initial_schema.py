"""Initial schema: topic tree, documents, conversation classifications, ingestion runs.

Revision ID: b4351a8aac09
Revises:
Create Date: 2026-07-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4351a8aac09"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the initial schema."""
    op.create_table(
        "document",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "ingestion_run",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("running", "success", "failed", name="ingestionrunstatus", native_enum=False, length=10),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("conversations_processed", sa.Integer(), nullable=False),
        sa.Column("conversations_failed", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "processed_conversation",
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("source_created_at", sa.DateTime(), nullable=False),
        sa.Column("processed_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("conversation_id"),
    )
    op.create_index(
        op.f("ix_processed_conversation_source"), "processed_conversation", ["source"], unique=False
    )
    op.create_index(
        op.f("ix_processed_conversation_source_created_at"),
        "processed_conversation",
        ["source_created_at"],
        unique=False,
    )
    op.create_table(
        "topic",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "type", sa.Enum("node", "leaf", name="topictype", native_enum=False, length=10), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["parent_id"], ["topic.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("parent_id", "name", name="uq_topic_parent_name"),
    )
    # Leaf names are globally unique (not just per-parent): restructuring re-parents leaves by
    # matching their name, so duplicate leaf names elsewhere in the tree would be ambiguous.
    op.create_index(
        "uq_topic_leaf_name", "topic", ["name"], unique=True, postgresql_where=sa.text("type = 'leaf'")
    )
    op.create_table(
        "conversation_topic",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("topic_id", sa.Integer(), nullable=False),
        sa.Column(
            "resolution",
            sa.Enum(
                "resolved", "partial", "unresolved", "unknown", name="resolution", native_enum=False, length=12
            ),
            nullable=False,
        ),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["topic_id"], ["topic.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", "topic_id", name="uq_conversation_topic"),
    )
    op.create_index(
        op.f("ix_conversation_topic_conversation_id"), "conversation_topic", ["conversation_id"], unique=False
    )
    op.create_index(op.f("ix_conversation_topic_topic_id"), "conversation_topic", ["topic_id"], unique=False)
    op.create_table(
        "topic_document",
        sa.Column("topic_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["document.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["topic_id"], ["topic.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("topic_id", "document_id"),
    )


def downgrade() -> None:
    """Drop the initial schema."""
    op.drop_table("topic_document")
    op.drop_index(op.f("ix_conversation_topic_topic_id"), table_name="conversation_topic")
    op.drop_index(op.f("ix_conversation_topic_conversation_id"), table_name="conversation_topic")
    op.drop_table("conversation_topic")
    op.drop_index("uq_topic_leaf_name", table_name="topic")
    op.drop_table("topic")
    op.drop_index(op.f("ix_processed_conversation_source_created_at"), table_name="processed_conversation")
    op.drop_index(op.f("ix_processed_conversation_source"), table_name="processed_conversation")
    op.drop_table("processed_conversation")
    op.drop_table("ingestion_run")
    op.drop_table("document")
