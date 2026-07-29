"""LLM (AnthropicBedrock) client dependency."""

from typing import Annotated

from anthropic import AnthropicBedrock
from fastapi import Depends
from starlette.requests import Request


def get_llm_client(request: Request) -> AnthropicBedrock:
    """Get the shared AnthropicBedrock client."""
    return request.app.state.llm_client


llm_client_dep = Annotated[AnthropicBedrock, Depends(get_llm_client)]
