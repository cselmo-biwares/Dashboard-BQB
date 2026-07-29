"""Conversation ingestion pipeline routes."""

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy import select

from app.audit import ACTION_INGESTION_TRIGGER, ACTION_INGESTION_UNPROCESS, log_action
from app.db.models import IngestionRun
from app.dependencies.auth import current_user_dep, require_editor
from app.dependencies.config import settings_dep
from app.dependencies.conversation_manager import conversation_manager_client_dep
from app.dependencies.db import db_session_dep
from app.dependencies.llm import llm_client_dep
from app.dependencies.redis import redis_dep
from app.ingestion import service
from app.schemas.ingestion import (
    IngestionRunOut,
    IngestionUpdateAccepted,
    IngestionUpdateRequest,
    UnprocessRequest,
    UnprocessResult,
)

router = APIRouter(prefix="/ingestion", tags=["ingestion"], dependencies=[Depends(require_editor)])


@router.post("/update", status_code=status.HTTP_202_ACCEPTED, response_model=IngestionUpdateAccepted)
async def trigger_update(
    background_tasks: BackgroundTasks,
    request: Request,
    session: db_session_dep,
    redis_client: redis_dep,
    conversation_manager_client: conversation_manager_client_dep,
    llm_client: llm_client_dep,
    settings: settings_dep,
    actor: current_user_dep,
    payload: IngestionUpdateRequest | None = None,
):
    """
    Trigger an ingestion run in the background.

    `payload` is optional — omit it (or send an empty body) for the automatic incremental
    window; set any of its fields to override that run's window/filters (see
    IngestionUpdateRequest).

    :return: 202 with the created run id; 409 if a run is already in progress
    """
    token = uuid.uuid4().hex
    acquired = await service.try_acquire_lock(redis_client, token, settings.ingestion.lock_ttl_seconds)
    if not acquired:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An ingestion run is already in progress")

    run = await service.start_run(session)
    sessionmaker = request.app.state.db_sessionmaker

    filters = (
        service.IngestionFilters(
            source=payload.source,
            status=payload.status,
            billable=payload.billable,
            created_date_from=payload.created_date_from,
            created_date_to=payload.created_date_to,
            min_age_hours=payload.min_age_hours,
            page_size=payload.page_size,
        )
        if payload is not None
        else None
    )

    async def _run_and_release():
        try:
            await service.run_ingestion(
                run.id,
                sessionmaker,
                conversation_manager_client,
                llm_client,
                settings.bedrock,
                settings.ingestion,
                filters,
            )
        finally:
            await service.release_lock(redis_client, token)

    background_tasks.add_task(_run_and_release)
    await log_action(
        session, actor.username, actor.role, ACTION_INGESTION_TRIGGER, detail=f"run_id={run.id}", request=request
    )
    return IngestionUpdateAccepted(run_id=run.id)


@router.post("/unprocess", response_model=UnprocessResult)
async def unprocess(payload: UnprocessRequest, request: Request, session: db_session_dep, actor: current_user_dep):
    """Un-process conversations matching the filter: as if they'd never been ingested.

    Doesn't reach out to the Conversation Manager or re-run classification — it only removes
    the local processed marker and topic assignments. To actually reclassify them, trigger
    /ingestion/update afterwards with created_date_from/to covering the same window (the
    automatic incremental window won't pick them back up on its own).
    """
    if payload.source is None and payload.created_date_from is None and payload.created_date_to is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one filter is required")

    affected, removed = await service.unprocess_conversations(
        session, payload.source, payload.created_date_from, payload.created_date_to
    )
    await log_action(
        session,
        actor.username,
        actor.role,
        ACTION_INGESTION_UNPROCESS,
        detail=(
            f"source={payload.source} from={payload.created_date_from} to={payload.created_date_to} affected={affected}"
        ),
        request=request,
    )
    return UnprocessResult(conversations_affected=affected, topic_assignments_removed=removed)


@router.get("/runs/latest", response_model=IngestionRunOut)
async def get_latest_run(session: db_session_dep):
    """Get the most recent ingestion run."""
    result = await session.execute(select(IngestionRun).order_by(IngestionRun.id.desc()).limit(1))
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No ingestion runs yet")
    return run


@router.get("/runs/{run_id}", response_model=IngestionRunOut)
async def get_run(run_id: int, session: db_session_dep):
    """Get the status of a specific ingestion run."""
    run = await session.get(IngestionRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingestion run not found")
    return run
