"""Topic tree schemas: explorer, resolution ranking, per-leaf drill-down."""

import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ResolutionBreakdown(BaseModel):
    """Count of conversations by resolution status."""

    resolved: int = 0
    partial: int = 0
    unresolved: int = 0
    unknown: int = 0


class TopicNode(BaseModel):
    """A node or leaf of the topic tree, with aggregated conversation counts."""

    id: int | None = Field(description="Topic id (None for the synthetic root)", default=None)
    name: str
    type: Literal["node", "leaf"]
    document_count: int = Field(description="Documents assigned (leaves only)", default=0)
    conversation_count: int = Field(description="Conversations assigned, summed over descendants", default=0)
    resolution_breakdown: ResolutionBreakdown = Field(default_factory=ResolutionBreakdown)
    children: list["TopicNode"] = Field(default_factory=list)


TopicNode.model_rebuild()


class ResolutionSummaryRow(BaseModel):
    """One row of the resolution ranking, per leaf."""

    topic_id: int
    leaf_path: str
    total_conversations: int
    resolved: int
    partial: int
    unresolved: int
    unknown: int
    resolution_rate: float = Field(description="resolved / total_conversations")
    has_documentation: bool = Field(description="False = conversations but no RAG doc assigned (gap)")


class ConversationTopicOut(BaseModel):
    """A conversation assigned to a leaf, for drill-down."""

    model_config = ConfigDict(from_attributes=True)

    conversation_id: int
    resolution: str
    reasoning: str
    created_at: datetime.datetime


class ConversationTopicPage(BaseModel):
    """A page of conversations assigned to a topic (leaf or node, aggregated over its leaves)."""

    total: int = Field(description="Total conversations matching, across all pages")
    items: list[ConversationTopicOut]


class TopicOut(BaseModel):
    """A single node/leaf, without aggregates — the result of a manual tree edit."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    parent_id: int | None
    name: str
    type: Literal["node", "leaf"]


class TopicCreateIn(BaseModel):
    """A new node or leaf to create by hand (not via LLM classification)."""

    parent_id: int | None = Field(description="Parent node id, or None to attach directly under the root")
    name: str = Field(min_length=1, max_length=255)
    type: Literal["node", "leaf"]


class TopicRenameIn(BaseModel):
    """New name for an existing node or leaf."""

    name: str = Field(min_length=1, max_length=255)


class TopicMoveIn(BaseModel):
    """New parent for an existing node or leaf (drag & drop re-parenting)."""

    parent_id: int | None = Field(description="New parent node id, or None to attach directly under the root")


class RootCauseResult(BaseModel):
    """Root-cause analysis for why a topic's partial/unresolved conversations end up that way."""

    topic_id: int
    leaf_path: str
    resolution: Literal["partial", "unresolved"]
    total_matching: int = Field(description="Total conversations with this resolution for this topic/period")
    sample_size: int = Field(description="How many of those were actually sent to the LLM")
    main_cause: str
    explanation: str
    secondary_causes: list[str] = Field(default_factory=list)


class ActivityHeatmapCell(BaseModel):
    """Conversation activity for one (day-of-week, hour) bucket, in local (Buenos Aires) time."""

    day_of_week: int = Field(description="0=Monday .. 6=Sunday")
    hour: int = Field(description="0-23, local time")
    total: int = Field(description="Total conversations observed in this bucket over the period")
    average: float = Field(description="total / how many times that weekday occurred in the period")


class ActivityHeatmapResult(BaseModel):
    """Average conversation volume by hour-of-day and day-of-week, for one topic (or the whole tree)."""

    topic_id: int | None = Field(description="None for the whole-tree (root) heatmap")
    leaf_path: str
    total_conversations: int = Field(description="Distinct conversations counted, across the whole period")
    cells: list[ActivityHeatmapCell] = Field(description="Always 168 entries (7 days x 24 hours)")


class RestructureRequest(BaseModel):
    """Optional instruction guiding the node restructure."""

    instruction: str | None = Field(description="Extra guidance for the reorganization", default=None)


class RestructureResult(BaseModel):
    """Outcome of a successful restructure."""

    leaves_kept: int
