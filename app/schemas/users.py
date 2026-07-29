"""Editor/analyst account management schemas (admin only)."""

import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import UserRole


class UserIn(BaseModel):
    """A new editor/analyst account."""

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8)
    role: UserRole


class UserUpdateIn(BaseModel):
    """Partial update of an existing account. Omitted fields are left unchanged."""

    password: str | None = Field(default=None, min_length=8)
    role: UserRole | None = None


class UserOut(BaseModel):
    """A stored editor/analyst account (never includes the password hash)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: UserRole
    created_at: datetime.datetime
    updated_at: datetime.datetime
