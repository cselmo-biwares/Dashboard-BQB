"""Conversation detail schema: transcript proxied from the Conversation Manager + our classification."""

import datetime

from pydantic import BaseModel


class ConversationMessageOut(BaseModel):
    """A single message in the transcript."""

    id: int
    role: str
    timestamp: datetime.datetime
    content: str | None


class ConversationTopicAssignment(BaseModel):
    """A topic this conversation was classified into."""

    leaf_path: str
    resolution: str
    reasoning: str


class ConversationDetailOut(BaseModel):
    """Full conversation detail: transcript + our topic classification."""

    id: int
    source: str
    status: str
    billable: bool
    created_at: datetime.datetime
    closed_at: datetime.datetime | None
    messages: list[ConversationMessageOut]
    topics: list[ConversationTopicAssignment]
