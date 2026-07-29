"""Editor/analyst account management. Admin only — see app.dependencies.auth.require_admin."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from starlette.requests import Request

from app.audit import ACTION_USER_CREATE, ACTION_USER_DELETE, ACTION_USER_UPDATE, log_action
from app.auth import hash_password
from app.db.models import User
from app.dependencies.auth import current_user_dep, require_admin
from app.dependencies.config import settings_dep
from app.dependencies.db import db_session_dep
from app.schemas.users import UserIn, UserOut, UserUpdateIn

router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(require_admin)])


@router.get("", response_model=list[UserOut])
async def list_users(session: db_session_dep):
    """List all editor/analyst accounts (the admin itself never has a row here)."""
    return (await session.execute(select(User).order_by(User.username))).scalars().all()


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserIn, request: Request, session: db_session_dep, settings: settings_dep, actor: current_user_dep
):
    """Create a new editor/analyst account."""
    if payload.username == settings.auth.admin_username:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username is reserved for the admin account")

    user = User(username=payload.username, password_hash=hash_password(payload.password), role=payload.role)
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as e:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists") from e

    await log_action(
        session,
        actor.username,
        actor.role,
        ACTION_USER_CREATE,
        detail=f"{user.username} ({user.role.value})",
        request=request,
    )
    await session.refresh(user)
    return user


@router.put("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    payload: UserUpdateIn,
    request: Request,
    session: db_session_dep,
    actor: current_user_dep,
):
    """Update an existing account's password and/or role."""
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if payload.password is not None:
        user.password_hash = hash_password(payload.password)
    if payload.role is not None:
        user.role = payload.role
    await session.flush()

    await log_action(session, actor.username, actor.role, ACTION_USER_UPDATE, detail=user.username, request=request)
    await session.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, request: Request, session: db_session_dep, actor: current_user_dep):
    """Delete an editor/analyst account."""
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    username = user.username
    await session.delete(user)
    await log_action(session, actor.username, actor.role, ACTION_USER_DELETE, detail=username, request=request)
