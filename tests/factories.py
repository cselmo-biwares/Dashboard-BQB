"""Test factories for Conversation Manager schemas."""

import datetime

from chatmessaging.http.schemas.convmanager import Conversation, Message


def make_conversation(conversation_id: int, hours_ago: int, source: str = "channel-manager-widget") -> Conversation:
    """Build a Conversation created `hours_ago` hours before now."""
    now = datetime.datetime.now(datetime.timezone.utc)
    created_at = now - datetime.timedelta(hours=hours_ago)
    return Conversation(
        source=source,
        external_reference=f"ref{conversation_id}",
        conv_metadata=None,
        id=conversation_id,
        status="closed_timeout",
        billable=False,
        created_at=created_at,
        closed_at=created_at,
    )


def make_message(
    conversation_id: int,
    message_id: str,
    role: str,
    content: str,
    timestamp: datetime.datetime,
    message_pk: int = 1,
) -> Message:
    """Build a Message for a conversation."""
    return Message(
        id=message_pk,
        conversation_id=conversation_id,
        external_message_id=message_id,
        timestamp=timestamp,
        role=role,
        content=content,
    )
