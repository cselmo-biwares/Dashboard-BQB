"""Audit log viewing route. Admin only — see app.dependencies.auth.require_admin."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.db.models import AuditLog
from app.dependencies.auth import require_admin
from app.dependencies.db import db_session_dep
from app.schemas.audit import AuditLogOut

router = APIRouter(prefix="/audit", tags=["audit"], dependencies=[Depends(require_admin)])


@router.get("", response_model=list[AuditLogOut])
async def list_audit_log(
    session: db_session_dep,
    username: Annotated[str | None, Query(description="Filter by exact username")] = None,
    action: Annotated[str | None, Query(description="Filter by exact action")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """List login events and data-modifying operations, newest first."""
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc())
    if username is not None:
        stmt = stmt.where(AuditLog.username == username)
    if action is not None:
        stmt = stmt.where(AuditLog.action == action)
    stmt = stmt.offset(offset).limit(limit)
    return (await session.execute(stmt)).scalars().all()
