"""Declarative base and engine/session factory for the destination Postgres."""

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def create_engine(db_url: str) -> AsyncEngine:
    """
    Create the async SQLAlchemy engine for the destination database.

    :param db_url: destination Postgres URL (async driver)
    :return: async engine
    """
    return create_async_engine(db_url)


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """
    Create an async session factory bound to an engine.

    :param engine: async engine
    :return: async session factory
    """
    return async_sessionmaker(engine, expire_on_commit=False)
