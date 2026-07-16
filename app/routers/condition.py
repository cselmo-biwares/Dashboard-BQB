"""Application condition status routes."""

from fastapi import APIRouter
from fastapi import Response, status
from redis.exceptions import RedisError

from app.dependencies.config import settings_dep, configurator_client_dep
from app.dependencies.redis import redis_dep

router = APIRouter(
    prefix="/status",
    tags=["status"],
)


@router.get("/liveness")
async def liveness():
    """
    Get application liveness status.

    :return: Status code
    """
    # TODO: Implement this
    return Response(status_code=status.HTTP_200_OK)


@router.get("/startup")
async def startup():
    """
    Get application startup status.

    :return: Status code
    """
    # TODO: Implement this
    return Response(status_code=status.HTTP_200_OK)


@router.get("/readiness")
async def readiness(settings: settings_dep, redis_client: redis_dep, configurator_client: configurator_client_dep):
    """
    Get application readiness status.

    :return: Status code
    """
    try:
        await redis_client.ping()
    except RedisError:
        return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)

    if settings.configurator.enabled and not await configurator_client.ping():
        return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)

    return Response(status_code=status.HTTP_200_OK)
