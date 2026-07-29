"""Conversation Manager client dependency."""

from typing import Annotated

from chatmessaging.http.client.convmanager import ConversationManagerClient
from fastapi import Depends
from starlette.requests import Request


def get_conversation_manager_client(request: Request) -> ConversationManagerClient:
    """Get the shared Conversation Manager client."""
    return request.app.state.conversation_manager_client


conversation_manager_client_dep = Annotated[ConversationManagerClient, Depends(get_conversation_manager_client)]
