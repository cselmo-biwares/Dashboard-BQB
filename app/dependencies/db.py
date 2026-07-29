"""Destination database dependencies."""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request


async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Get a request-scoped database session from the app's session factory."""
    sessionmaker = request.app.state.db_sessionmaker
    async with sessionmaker() as session:
        yield session


db_session_dep = Annotated[AsyncSession, Depends(get_db_session)]
