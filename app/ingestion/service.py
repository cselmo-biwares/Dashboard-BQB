"""Conversation ingestion pipeline: incremental window fetch, classification, run tracking.

Only fetches conversations in the window (watermark, now - min_age_hours], paginating the
Conversation Manager instead of re-reading everything on every run.
"""

import asyncio
import datetime
import logging
from dataclasses import dataclass

from anthropic import AnthropicBedrock
from chatmessaging.http.client.convmanager import ConversationManagerClient
from chatmessaging.http.schemas.convmanager import Conversation, ListConversationsFilter, Message
from redis.asyncio import Redis
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import BedrockSettings, IngestionSettings
from app.db.models import ConversationTopic, IngestionRun, IngestionRunStatus, ProcessedConversation
from app.ingestion import llm as llm_module
from app.ingestion.tree import apply_conversation_classification, load_full_tree_from_db

logger = logging.getLogger(__name__)

LOCK_KEY = "ingestion:lock"

# ListConversationsFilter defaults created_date_from to "now - 30 days" when omitted, so on
# the first run (no watermark yet) we must pass an explicit wide lower bound ourselves —
# otherwise anything older than 30 days would be silently skipped, forever (the watermark
# only ever moves forward from whatever that first run captured).
EPOCH = datetime.datetime(2000, 1, 1, tzinfo=datetime.timezone.utc)


@dataclass
class IngestionFilters:
    """Optional overrides for a single run, mirroring ListConversationsFilter.

    Any field left as None falls back to the automatic behavior (incremental watermark,
    configured min_age_hours/page_size, no source/status/billable filter).
    """

    source: str | None = None
    status: str | None = None
    billable: bool | None = None
    created_date_from: datetime.datetime | None = None
    created_date_to: datetime.datetime | None = None
    min_age_hours: int | None = None
    page_size: int | None = None


async def reap_stale_runs(session: AsyncSession, redis_client: Redis) -> int:
    """Clean up state left behind by a process that died mid-ingestion.

    Called once at app startup: any 'running' ingestion_run row is necessarily stale (this
    is a fresh process, nothing is actually running yet), so mark it failed — otherwise it
    stays 'running' forever and the front's trigger button stays disabled forever. Also
    force-clear the Redis lock unconditionally, since whoever held it is gone too.

    :return: number of runs reaped
    """
    result = await session.execute(
        update(IngestionRun)
        .where(IngestionRun.status == IngestionRunStatus.RUNNING)
        .values(
            status=IngestionRunStatus.FAILED,
            error="Interrupted: the server restarted while this run was in progress.",
            finished_at=datetime.datetime.now(datetime.timezone.utc),
        )
    )
    await session.commit()
    await redis_client.delete(LOCK_KEY)
    if result.rowcount:
        logger.warning("Reaped %s stale ingestion run(s) left 'running' by a previous process", result.rowcount)
    return result.rowcount


async def try_acquire_lock(redis_client: Redis, token: str, ttl_seconds: int) -> bool:
    """Try to acquire the ingestion lock. Returns True if acquired, False if already held."""
    return bool(await redis_client.set(LOCK_KEY, token, nx=True, ex=ttl_seconds))


async def release_lock(redis_client: Redis, token: str) -> None:
    """Release the ingestion lock, but only if we still own it."""
    current = await redis_client.get(LOCK_KEY)
    if isinstance(current, bytes):
        current = current.decode()
    if current == token:
        await redis_client.delete(LOCK_KEY)


async def start_run(session: AsyncSession) -> IngestionRun:
    """Create and persist a new 'running' ingestion_run row."""
    run = IngestionRun(status=IngestionRunStatus.RUNNING)
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def _fetch_window(
    client: ConversationManagerClient,
    created_date_from: datetime.datetime,
    created_date_to: datetime.datetime,
    page_size: int,
    source: str | None = None,
    status: str | None = None,
    billable: bool | None = None,
) -> list[Conversation]:
    """Page through the Conversation Manager for conversations in the incremental window."""
    conversations: list[Conversation] = []
    from_id: int | None = None
    while True:
        kwargs: dict = {
            "created_date_from": created_date_from,
            "created_date_to": created_date_to,
            "result_size": page_size,
        }
        if source is not None:
            kwargs["source"] = source
        if status is not None:
            kwargs["status"] = status
        if billable is not None:
            kwargs["billable"] = billable
        if from_id is not None:
            kwargs["from_id"] = from_id

        page = await client.list_conversations(ListConversationsFilter(**kwargs))
        if not page:
            break
        conversations.extend(page)
        if len(page) < page_size:
            break

        next_from_id = min(c.id for c in page)
        if from_id is not None and next_from_id >= from_id:
            break  # safety net: avoid looping forever if pagination doesn't advance
        from_id = next_from_id

    return conversations


def _conversation_full_text(messages: list[Message]) -> str:
    return "\n".join(f"[{m.role.upper()}]: {m.content or ''}" for m in messages)


async def _get_watermark(session: AsyncSession) -> datetime.datetime | None:
    result = await session.execute(select(func.max(ProcessedConversation.source_created_at)))
    return result.scalar_one_or_none()


async def _process_conversation(
    session: AsyncSession,
    conversation_manager_client: ConversationManagerClient,
    llm_client: AnthropicBedrock,
    bedrock_settings: BedrockSettings,
    conversation: Conversation,
) -> None:
    messages = await conversation_manager_client.get_messages(conversation.id)
    full_text = _conversation_full_text(messages)

    if full_text.strip():
        tree = await load_full_tree_from_db(session)
        system_prompt = await llm_module.get_prompt(session, llm_module.PROMPT_KEY_CLASSIFY_CONVERSATION)
        classification = await asyncio.to_thread(
            llm_module.classify_conversation,
            llm_client,
            bedrock_settings,
            tree,
            conversation.id,
            full_text,
            system_prompt,
        )
        await apply_conversation_classification(session, conversation.id, classification)

    session.add(
        ProcessedConversation(
            conversation_id=conversation.id,
            source=conversation.source,
            source_created_at=conversation.created_at,
        )
    )
    await session.commit()


async def unprocess_conversations(
    session: AsyncSession,
    source: str | None,
    created_date_from: datetime.datetime | None,
    created_date_to: datetime.datetime | None,
) -> tuple[int, int]:
    """Delete the local processing record for conversations matching the filter.

    Removes their conversation_topic assignments and their ProcessedConversation marker, so
    the system treats them as never having been processed. Doesn't touch the source data in
    the Conversation Manager: re-running /ingestion/update with created_date_from/to covering
    the same window will fetch and reclassify them again (the automatic incremental window
    won't reach back on its own, since the watermark only ever moves forward).

    :return: (conversations affected, conversation_topic rows removed with them)
    """
    query = select(ProcessedConversation.conversation_id)
    if source is not None:
        query = query.where(ProcessedConversation.source == source)
    if created_date_from is not None:
        query = query.where(ProcessedConversation.source_created_at >= created_date_from)
    if created_date_to is not None:
        query = query.where(ProcessedConversation.source_created_at <= created_date_to)

    conversation_ids = [row[0] for row in (await session.execute(query)).all()]
    if not conversation_ids:
        return 0, 0

    topic_result = await session.execute(
        delete(ConversationTopic).where(ConversationTopic.conversation_id.in_(conversation_ids))
    )
    await session.execute(
        delete(ProcessedConversation).where(ProcessedConversation.conversation_id.in_(conversation_ids))
    )
    await session.commit()
    return len(conversation_ids), topic_result.rowcount


async def run_ingestion(
    run_id: int,
    sessionmaker: async_sessionmaker[AsyncSession],
    conversation_manager_client: ConversationManagerClient,
    llm_client: AnthropicBedrock,
    bedrock_settings: BedrockSettings,
    ingestion_settings: IngestionSettings,
    filters: IngestionFilters | None = None,
) -> None:
    """Run one ingestion pass: fetch the window, classify each conversation, track results.

    `filters` lets a single run override the automatic window (watermark/cutoff/page size)
    and add source/status/billable filters — see IngestionFilters. A failure on a single
    conversation is logged and counted, but doesn't abort the run.
    """
    filters = filters or IngestionFilters()
    processed = 0
    failed = 0

    try:
        async with sessionmaker() as session:
            min_age_hours = (
                filters.min_age_hours if filters.min_age_hours is not None else ingestion_settings.min_age_hours
            )
            cutoff = filters.created_date_to or (
                datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=min_age_hours)
            )
            if filters.created_date_from is not None:
                effective_from = filters.created_date_from
            else:
                watermark = await _get_watermark(session)
                effective_from = watermark or EPOCH
            page_size = filters.page_size or ingestion_settings.page_size

            conversations = await _fetch_window(
                conversation_manager_client,
                effective_from,
                cutoff,
                page_size,
                source=filters.source,
                status=filters.status,
                billable=filters.billable,
            )

            already_processed: set[int] = set()
            if conversations:
                ids = [c.id for c in conversations]
                rows = await session.execute(
                    select(ProcessedConversation.conversation_id).where(ProcessedConversation.conversation_id.in_(ids))
                )
                already_processed = {r[0] for r in rows}

            for conversation in conversations:
                if conversation.id in already_processed:
                    continue
                try:
                    await _process_conversation(
                        session, conversation_manager_client, llm_client, bedrock_settings, conversation
                    )
                    processed += 1
                except Exception:
                    logger.exception("Failed to process conversation #%s", conversation.id)
                    await session.rollback()
                    failed += 1

            run = await session.get(IngestionRun, run_id)
            run.status = IngestionRunStatus.SUCCESS
            run.conversations_processed = processed
            run.conversations_failed = failed
            run.finished_at = datetime.datetime.now(datetime.timezone.utc)
            await session.commit()
    except Exception as e:
        logger.exception("Ingestion run #%s failed", run_id)
        async with sessionmaker() as session:
            run = await session.get(IngestionRun, run_id)
            if run is not None:
                run.status = IngestionRunStatus.FAILED
                run.conversations_processed = processed
                run.conversations_failed = failed
                run.error = str(e)
                run.finished_at = datetime.datetime.now(datetime.timezone.utc)
                await session.commit()
