"""Conversation ingestion run schemas."""

import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ConversationStatusLiteral = Literal[
    "in_progress", "closed_timeout", "closed_assistant", "closed_operator", "redirected"
]


class IngestionUpdateRequest(BaseModel):
    """Optional filters for a run, mirroring chatmessaging's ListConversationsFilter.

    Everything is optional: omitted fields fall back to the automatic incremental window
    (watermark → now - min_age_hours) and the configured page size — same behavior as
    triggering the update with no body at all.
    """

    source: str | None = Field(default=None, description="Filter by conversation channel")
    status: ConversationStatusLiteral | None = Field(default=None, description="Filter by conversation status")
    billable: bool | None = Field(default=None, description="Filter by billable flag")
    created_date_from: datetime.datetime | None = Field(
        default=None, description="Overrides the automatic watermark for this run"
    )
    created_date_to: datetime.datetime | None = Field(
        default=None, description="Overrides the automatic (now - min_age_hours) cutoff for this run"
    )
    min_age_hours: int | None = Field(
        default=None, gt=0, description="Overrides settings.ingestion.min_age_hours; ignored if created_date_to is set"
    )
    page_size: int | None = Field(
        default=None, gt=0, le=50, description="Overrides settings.ingestion.page_size for this run"
    )


class IngestionUpdateAccepted(BaseModel):
    """Response for a successfully scheduled ingestion run."""

    run_id: int


class IngestionRunOut(BaseModel):
    """Status of one ingestion run."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    started_at: datetime.datetime
    finished_at: datetime.datetime | None
    conversations_processed: int
    conversations_failed: int
    error: str | None


class UnprocessRequest(BaseModel):
    """Filter selecting which already-processed conversations to un-process.

    At least one field must be set — an unfiltered "un-process everything" isn't supported
    here on purpose, to keep this from being a one-click full reset.
    """

    source: str | None = Field(default=None, description="Filter by conversation channel")
    created_date_from: datetime.datetime | None = Field(
        default=None, description="Filter by source_created_at, lower bound"
    )
    created_date_to: datetime.datetime | None = Field(
        default=None, description="Filter by source_created_at, upper bound"
    )


class UnprocessResult(BaseModel):
    """Outcome of un-processing a batch of conversations."""

    conversations_affected: int = Field(description="Conversations whose processed marker was removed")
    topic_assignments_removed: int = Field(description="conversation_topic rows removed along with them")
