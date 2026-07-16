"""Module for all input/output schemas."""

from pydantic import BaseModel, ConfigDict, Field


class RootOutput(BaseModel):
    """Root endpoint output schema. Allows only public info from settings."""

    model_config = ConfigDict(extra="ignore")
    app_name: str = Field(description="Human readable service name")
    configurable_int: int
    configurable_str: str
