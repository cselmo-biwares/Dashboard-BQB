"""Redis dependencies."""

from typing import Annotated

import redis.asyncio as redis
from fastapi import Depends
from starlette.requests import Request


def get_redis(request: Request) -> redis.Redis:
    """Get the shared Redis client."""
    return request.app.state.redis


redis_dep = Annotated[redis.Redis, Depends(get_redis)]
