"""Login route. Every attempt (success or failure) is recorded in the audit log."""

from fastapi import APIRouter, HTTPException, status
from starlette.requests import Request

from app.audit import ACTION_LOGIN_FAILED, ACTION_LOGIN_SUCCESS, log_action
from app.auth import authenticate, create_access_token
from app.dependencies.config import settings_dep
from app.dependencies.db import db_session_dep
from app.schemas.auth import LoginRequest, LoginResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, request: Request, session: db_session_dep, settings: settings_dep):
    """Authenticate and issue a session token, logging the attempt either way."""
    user = await authenticate(payload.username, payload.password, session, settings)
    if user is None:
        await log_action(session, payload.username, "unknown", ACTION_LOGIN_FAILED, request=request)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    await log_action(session, user.username, user.role, ACTION_LOGIN_SUCCESS, request=request)
    token = create_access_token(user.username, settings.auth)
    return LoginResponse(access_token=token, username=user.username, role=user.role)
