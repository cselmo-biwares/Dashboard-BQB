"""Login request/response schemas."""

from pydantic import BaseModel

from app.auth import Role


class LoginRequest(BaseModel):
    """Credentials submitted to /auth/login."""

    username: str
    password: str


class LoginResponse(BaseModel):
    """Issued session token plus the identity it resolves to."""

    access_token: str
    token_type: str = "bearer"
    username: str
    role: Role
