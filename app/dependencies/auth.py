"""Auth dependencies: resolve the current user from the Authorization header, gate by role."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth import AuthenticatedUser, InvalidTokenError, Role, decode_username, resolve_user
from app.dependencies.config import settings_dep
from app.dependencies.db import db_session_dep

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    session: db_session_dep,
    settings: settings_dep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AuthenticatedUser:
    """Resolve the authenticated caller from the Bearer token, or raise 401."""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        username = decode_username(credentials.credentials, settings.auth)
    except InvalidTokenError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session") from e

    user = await resolve_user(username, session, settings)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account no longer exists")
    return user


current_user_dep = Annotated[AuthenticatedUser, Depends(get_current_user)]


def require_roles(*roles: Role):
    """Dependency factory: 403 unless the current user's role is one of `roles`."""

    async def _check(user: current_user_dep) -> AuthenticatedUser:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed for your role")
        return user

    return _check


require_admin = require_roles("admin")
require_editor = require_roles("admin", "editor")
require_any_role = require_roles("admin", "editor", "analyst")
