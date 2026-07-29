"""Audit logging: login events and data-modifying operations, for the admin's activity view.

Deliberately narrow in scope — only login/logout and write operations are logged, not every
read request, to keep the log itself readable instead of an undifferentiated access log.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.db.models import AuditLog

ACTION_LOGIN_SUCCESS = "login"
ACTION_LOGIN_FAILED = "login_failed"
ACTION_DOCUMENT_CREATE = "document.create"
ACTION_DOCUMENT_DELETE = "document.delete"
ACTION_TOPIC_DOCUMENT_UNASSIGN = "topic.document_unassign"
ACTION_TOPIC_RESTRUCTURE = "topic.restructure"
ACTION_TOPIC_CREATE = "topic.create"
ACTION_TOPIC_RENAME = "topic.rename"
ACTION_TOPIC_DELETE = "topic.delete"
ACTION_TOPIC_MOVE = "topic.move"
ACTION_INGESTION_TRIGGER = "ingestion.trigger"
ACTION_INGESTION_UNPROCESS = "ingestion.unprocess"
ACTION_PROMPT_UPDATE = "prompt.update"
ACTION_PROMPT_RESET = "prompt.reset"
ACTION_USER_CREATE = "user.create"
ACTION_USER_UPDATE = "user.update"
ACTION_USER_DELETE = "user.delete"
ACTION_NOTE_CREATE = "note.create"
ACTION_NOTE_UPDATE = "note.update"
ACTION_NOTE_DELETE = "note.delete"


def _client_ip(request: Request | None) -> str | None:
    return request.client.host if request is not None and request.client is not None else None


async def log_action(
    session: AsyncSession,
    username: str,
    role: str,
    action: str,
    detail: str | None = None,
    request: Request | None = None,
) -> None:
    """Record an audit_log entry and commit it immediately."""
    session.add(AuditLog(username=username, role=role, action=action, detail=detail, ip_address=_client_ip(request)))
    await session.commit()
