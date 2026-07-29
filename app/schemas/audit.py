"""Audit log viewing schemas (admin only)."""

import datetime

from pydantic import BaseModel, ConfigDict


class AuditLogOut(BaseModel):
    """A single audit log entry."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: str
    action: str
    detail: str | None
    ip_address: str | None
    created_at: datetime.datetime
