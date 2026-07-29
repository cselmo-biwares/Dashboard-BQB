"""Authentication: password hashing, JWT session tokens, and role resolution.

The single admin account is validated against env vars (settings.auth.admin_username /
admin_password) and never has a row in `user` — editor/analyst accounts are DB-managed
(see app.db.models.User).

Session tokens only carry the username; the role is always re-derived from the source of
truth (env for admin, DB for everyone else) on every request via `resolve_user`, instead of
trusting a cached role claim in the token. That way, an admin revoking access or changing
someone's role takes effect on their very next request, not whenever a 12h token happens
to expire.
"""

import datetime
import hmac
import logging
from typing import Literal

import bcrypt
import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import AuthSettings, Settings
from app.db.models import User

logger = logging.getLogger(__name__)

Role = Literal["admin", "editor", "analyst"]


class AuthenticatedUser:
    """The resolved identity of the caller for one request."""

    def __init__(self, username: str, role: Role, user_id: int | None = None):
        """Initialize with the resolved username/role (and DB id, None for the admin)."""
        self.username = username
        self.role = role
        self.user_id = user_id


class InvalidTokenError(Exception):
    """Raised when a session token is missing, malformed, or expired."""


def hash_password(password: str) -> str:
    """Hash a password for storage."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Check a plaintext password against a stored bcrypt hash."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(username: str, settings: AuthSettings) -> str:
    """Create a signed session token for `username` (no role claim — always re-derived)."""
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {"sub": username, "iat": now, "exp": now + datetime.timedelta(hours=settings.session_hours)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_username(token: str, settings: AuthSettings) -> str:
    """Decode and verify a session token, returning its username claim."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as e:
        raise InvalidTokenError(str(e)) from e
    username = payload.get("sub")
    if not username:
        raise InvalidTokenError("Token has no subject")
    return username


async def authenticate(
    username: str, password: str, session: AsyncSession, settings: Settings
) -> AuthenticatedUser | None:
    """Verify credentials against the admin env vars first, then the `user` table."""
    if username == settings.auth.admin_username and hmac.compare_digest(
        password.encode("utf-8"), settings.auth.admin_password.encode("utf-8")
    ):
        return AuthenticatedUser(username=username, role="admin")

    user = (await session.execute(select(User).where(User.username == username))).scalar_one_or_none()
    if user is not None and verify_password(password, user.password_hash):
        return AuthenticatedUser(username=user.username, role=user.role.value, user_id=user.id)

    return None


async def resolve_user(username: str, session: AsyncSession, settings: Settings) -> AuthenticatedUser | None:
    """Re-derive the current identity/role for `username` from the source of truth.

    Called on every authenticated request instead of trusting the token's cached claims,
    so a role change or account deletion by the admin takes effect immediately.
    """
    if username == settings.auth.admin_username:
        return AuthenticatedUser(username=username, role="admin")

    user = (await session.execute(select(User).where(User.username == username))).scalar_one_or_none()
    if user is None:
        return None
    return AuthenticatedUser(username=user.username, role=user.role.value, user_id=user.id)
