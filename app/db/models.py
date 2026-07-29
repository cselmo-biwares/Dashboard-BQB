"""SQLAlchemy ORM models for the destination database."""

import datetime
import enum

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TopicType(str, enum.Enum):
    """Kind of a topic tree node."""

    NODE = "node"
    LEAF = "leaf"


class Resolution(str, enum.Enum):
    """Resolution status of a conversation for a given topic."""

    RESOLVED = "resolved"
    PARTIAL = "partial"
    UNRESOLVED = "unresolved"
    UNKNOWN = "unknown"


class IngestionRunStatus(str, enum.Enum):
    """Status of an ingestion run."""

    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class UserRole(str, enum.Enum):
    """Role of a DB-managed account.

    The single admin account is *not* one of these — it's validated against env vars and
    never gets a row in `user` (see app.auth).
    """

    EDITOR = "editor"
    ANALYST = "analyst"


def _str_enum(enum_cls: type[enum.Enum], length: int) -> Enum:
    """Store a str Enum as plain VARCHAR + CHECK constraint, not a native Postgres ENUM type.

    So members round-trip as Python enum instances and adding a member is a plain migration.
    """
    return Enum(enum_cls, native_enum=False, length=length, values_callable=lambda e: [x.value for x in e])


class Topic(Base):
    """A node or leaf of the topic tree.

    Leaves are stable entities: restructuring only ever changes a node's parent/name,
    never a leaf's identity, so document/conversation assignments (which reference a
    leaf's id) are never affected by reorganizing the tree.
    """

    __tablename__ = "topic"
    __table_args__ = (
        UniqueConstraint("parent_id", "name", name="uq_topic_parent_name"),
        # Leaf names are globally unique (across the whole tree, not just per-parent): restructuring
        # re-parents leaves by matching their name, so ambiguous duplicate leaf names would break that.
        Index("uq_topic_leaf_name", "name", unique=True, postgresql_where=text("type = 'leaf'")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("topic.id", ondelete="CASCADE"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[TopicType] = mapped_column(_str_enum(TopicType, 10), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    children: Mapped[list["Topic"]] = relationship(back_populates="parent", cascade="all, delete-orphan")
    parent: Mapped["Topic | None"] = relationship(back_populates="children", remote_side=[id])


class Document(Base):
    """A RAG document that can be assigned to one or more topic leaves."""

    __tablename__ = "document"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TopicDocument(Base):
    """Assignment of a document to a topic leaf (many-to-many)."""

    __tablename__ = "topic_document"

    topic_id: Mapped[int] = mapped_column(ForeignKey("topic.id", ondelete="CASCADE"), primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("document.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConversationTopic(Base):
    """Assignment of a conversation to a topic leaf, with its resolution status."""

    __tablename__ = "conversation_topic"
    __table_args__ = (UniqueConstraint("conversation_id", "topic_id", name="uq_conversation_topic"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(nullable=False, index=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topic.id", ondelete="CASCADE"), nullable=False, index=True)
    resolution: Mapped[Resolution] = mapped_column(_str_enum(Resolution, 12), nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProcessedConversation(Base):
    """Tracks which conversations have already been ingested.

    So /ingestion/update only fetches the incremental window instead of re-reading everything.
    """

    __tablename__ = "processed_conversation"

    conversation_id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    processed_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PromptOverride(Base):
    """A user-edited override of one of the fixed LLM system prompts.

    Read fresh on every LLM call (no caching), so edits from the front take effect on
    the very next call without restarting the app. Absence of a row for a key means
    "use the hardcoded default" (see app.ingestion.llm.DEFAULT_PROMPTS).
    """

    __tablename__ = "prompt_override"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class User(Base):
    """An editor or analyst account, created/managed by the admin.

    The admin account itself lives in env vars, not here — see UserRole.
    """

    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(_str_enum(UserRole, 10), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AuditLog(Base):
    """Login events and data-modifying operations, for the admin's activity view.

    `username` is plain text, not a FK to `user`: it must also cover the admin (who has no
    row there) and must keep a deleted user's history readable after they're gone.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class AnalystNote(Base):
    """A freeform note, optionally saved from a topic's root-cause analysis.

    `leaf_path`/`resolution` are a snapshot taken at save time, not a live join: the note
    stays meaningful even after the topic is renamed, restructured, or deleted (`topic_id`
    goes to NULL via ON DELETE SET NULL, but the text context survives). `filter_*` is a
    snapshot of the global filter bar (channel/date range) active when the note was created,
    so a note saved from a scoped analysis stays traceable to the scope it was drawn from.
    """

    __tablename__ = "analyst_note"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    topic_id: Mapped[int | None] = mapped_column(ForeignKey("topic.id", ondelete="SET NULL"), nullable=True, index=True)
    leaf_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    resolution: Mapped[str | None] = mapped_column(String(12), nullable=True)
    filter_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    filter_from: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    filter_to: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class IngestionRun(Base):
    """A single execution of the conversation ingestion pipeline."""

    __tablename__ = "ingestion_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[IngestionRunStatus] = mapped_column(
        _str_enum(IngestionRunStatus, 10), nullable=False, default=IngestionRunStatus.RUNNING
    )
    started_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    conversations_processed: Mapped[int] = mapped_column(default=0)
    conversations_failed: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
