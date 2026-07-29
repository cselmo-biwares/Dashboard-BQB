"""Document ingestion schemas."""

import datetime

from pydantic import BaseModel, ConfigDict, Field


class DocumentIn(BaseModel):
    """A RAG document submitted for classification."""

    name: str = Field(description="Document name (e.g. 'tarifas.md'), used as upsert key")
    content: str = Field(description="Document content")


class DocumentOut(BaseModel):
    """A stored document."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    content: str
    created_at: datetime.datetime
    updated_at: datetime.datetime


class DocumentClassifyResult(BaseModel):
    """Result of classifying a document against the topic tree."""

    document: DocumentOut
    assigned_leaf_paths: list[str]
