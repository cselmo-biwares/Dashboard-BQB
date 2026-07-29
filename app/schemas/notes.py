"""Analyst notes: freeform, optionally saved from a topic's root-cause analysis."""

import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class NoteIn(BaseModel):
    """A new note, either standalone or saved from a root-cause analysis result."""

    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    topic_id: int | None = Field(description="Topic this note relates to, if any", default=None)
    leaf_path: str | None = Field(description="Snapshot of the topic's path at save time", default=None)
    resolution: Literal["partial", "unresolved"] | None = Field(
        description="Set when saved from a root-cause analysis", default=None
    )
    filter_source: str | None = Field(description="Channel filter active when this note was saved", default=None)
    filter_from: datetime.datetime | None = Field(description="Date-range filter active, start bound", default=None)
    filter_to: datetime.datetime | None = Field(description="Date-range filter active, end bound", default=None)


class NoteUpdateIn(BaseModel):
    """New title/content for an existing note. The topic/resolution/filter context never changes."""

    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)


class NoteOut(BaseModel):
    """A stored analyst note."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    content: str
    topic_id: int | None
    leaf_path: str | None
    resolution: Literal["partial", "unresolved"] | None
    filter_source: str | None
    filter_from: datetime.datetime | None
    filter_to: datetime.datetime | None
    created_by: str
    updated_by: str
    created_at: datetime.datetime
    updated_at: datetime.datetime
