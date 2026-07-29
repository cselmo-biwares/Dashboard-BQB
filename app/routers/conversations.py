"""Conversation detail: transcript proxied from the Conversation Manager + our topic classification."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.db.models import ConversationTopic
from app.dependencies.auth import require_any_role
from app.dependencies.conversation_manager import conversation_manager_client_dep
from app.dependencies.db import db_session_dep
from app.ingestion.tree import leaf_paths_by_id
from app.schemas.conversations import ConversationDetailOut, ConversationMessageOut, ConversationTopicAssignment

router = APIRouter(prefix="/conversations", tags=["conversations"], dependencies=[Depends(require_any_role)])


@router.get("/{conversation_id}", response_model=ConversationDetailOut)
async def get_conversation_detail(
    conversation_id: int,
    session: db_session_dep,
    conversation_manager_client: conversation_manager_client_dep,
):
    """Get a conversation's full transcript plus the topics we classified it into."""
    conversation = await conversation_manager_client.get_conversation(str(conversation_id))
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    messages = await conversation_manager_client.get_messages(conversation_id)

    assignments = (
        (await session.execute(select(ConversationTopic).where(ConversationTopic.conversation_id == conversation_id)))
        .scalars()
        .all()
    )
    paths = await leaf_paths_by_id(session, [a.topic_id for a in assignments])

    return ConversationDetailOut(
        id=conversation.id,
        source=conversation.source,
        status=conversation.status,
        billable=conversation.billable,
        created_at=conversation.created_at,
        closed_at=conversation.closed_at,
        messages=[
            ConversationMessageOut(id=m.id, role=m.role, timestamp=m.timestamp, content=m.content) for m in messages
        ],
        topics=[
            ConversationTopicAssignment(
                leaf_path=paths.get(a.topic_id, ""), resolution=a.resolution, reasoning=a.reasoning
            )
            for a in assignments
        ],
    )
