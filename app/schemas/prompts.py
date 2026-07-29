"""LLM system prompt schemas: front-editable overrides of the three fixed prompts."""

import datetime
from typing import Literal

from pydantic import BaseModel, Field

PromptKeyLiteral = Literal["classify_conversation", "classify_document", "restructure", "root_cause"]


class PromptOut(BaseModel):
    """Current value of one of the three system prompts."""

    key: PromptKeyLiteral
    content: str
    is_default: bool = Field(description="True if no override is stored (content is the hardcoded default)")
    updated_at: datetime.datetime | None = Field(description="None if using the default", default=None)


class PromptUpdateIn(BaseModel):
    """New content for a prompt override."""

    content: str
