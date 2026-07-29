"""Topic tree routes: explorer, resolution ranking, per-leaf drill-down, restructuring."""

import asyncio
import datetime
from collections import defaultdict
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import Select, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import (
    ACTION_TOPIC_CREATE,
    ACTION_TOPIC_DELETE,
    ACTION_TOPIC_DOCUMENT_UNASSIGN,
    ACTION_TOPIC_MOVE,
    ACTION_TOPIC_RENAME,
    ACTION_TOPIC_RESTRUCTURE,
    log_action,
)
from app.db.models import ConversationTopic, Document, ProcessedConversation, Topic, TopicDocument, TopicType
from app.dependencies.auth import current_user_dep, require_any_role, require_editor
from app.dependencies.config import settings_dep
from app.dependencies.db import db_session_dep
from app.dependencies.llm import llm_client_dep
from app.ingestion import llm as llm_module
from app.ingestion.tree import (
    TreeRestructureError,
    apply_restructure,
    is_within_subtree,
    leaf_ids_under,
    leaf_paths_by_id,
    load_tree_structure_from_db,
    topics_by_parent,
)
from app.schemas.documents import DocumentOut
from app.schemas.topics import (
    ActivityHeatmapCell,
    ActivityHeatmapResult,
    ConversationTopicPage,
    ResolutionBreakdown,
    ResolutionSummaryRow,
    RestructureRequest,
    RestructureResult,
    RootCauseResult,
    TopicCreateIn,
    TopicMoveIn,
    TopicNode,
    TopicOut,
    TopicRenameIn,
)

router = APIRouter(prefix="/topics", tags=["topics"], dependencies=[Depends(require_any_role)])

LOCAL_TZ = ZoneInfo("America/Argentina/Buenos_Aires")


def _apply_period_and_source(
    query: Select,
    date_from: datetime.datetime | None,
    date_to: datetime.datetime | None,
    source: str | None,
) -> tuple[Select, bool]:
    """Join ConversationTopic -> ProcessedConversation and filter by period/source, if any given.

    :return: (query, joined) — `joined` tells the caller whether the join was actually added
    """
    if date_from is None and date_to is None and source is None:
        return query, False
    query = query.join(
        ProcessedConversation, ProcessedConversation.conversation_id == ConversationTopic.conversation_id
    )
    if date_from is not None:
        query = query.where(ProcessedConversation.source_created_at >= date_from)
    if date_to is not None:
        query = query.where(ProcessedConversation.source_created_at <= date_to)
    if source is not None:
        query = query.where(ProcessedConversation.source == source)
    return query, True


async def _leaf_stats(
    session: AsyncSession,
    date_from: datetime.datetime | None = None,
    date_to: datetime.datetime | None = None,
    source: str | None = None,
) -> tuple[dict[int, int], dict[int, ResolutionBreakdown]]:
    doc_rows = (
        await session.execute(
            select(TopicDocument.topic_id, func.count(TopicDocument.document_id)).group_by(TopicDocument.topic_id)
        )
    ).all()
    doc_counts = dict(doc_rows)

    conv_query, _ = _apply_period_and_source(
        select(ConversationTopic.topic_id, ConversationTopic.resolution, func.count()), date_from, date_to, source
    )
    conv_query = conv_query.group_by(ConversationTopic.topic_id, ConversationTopic.resolution)
    conv_rows = (await session.execute(conv_query)).all()
    breakdowns: dict[int, ResolutionBreakdown] = defaultdict(ResolutionBreakdown)
    for topic_id, resolution, count in conv_rows:
        setattr(breakdowns[topic_id], resolution, count)
    return doc_counts, breakdowns


def _prune_empty(node: TopicNode) -> TopicNode | None:
    """Drop leaves with zero (period-scoped) conversations, and nodes left with no children.

    A surviving node's counts are recomputed from its surviving children only, so they stay
    consistent with what's actually visible in the pruned tree (e.g. a node's document_count
    never includes documents that only lived on a leaf that got pruned away).
    """
    if node.type == "leaf":
        return node if node.conversation_count > 0 else None
    pruned_children = [c for c in (_prune_empty(child) for child in node.children) if c is not None]
    if not pruned_children:
        return None
    return node.model_copy(
        update={
            "children": pruned_children,
            "document_count": sum(c.document_count for c in pruned_children),
            "conversation_count": sum(c.conversation_count for c in pruned_children),
            "resolution_breakdown": ResolutionBreakdown(
                resolved=sum(c.resolution_breakdown.resolved for c in pruned_children),
                partial=sum(c.resolution_breakdown.partial for c in pruned_children),
                unresolved=sum(c.resolution_breakdown.unresolved for c in pruned_children),
                unknown=sum(c.resolution_breakdown.unknown for c in pruned_children),
            ),
        }
    )


def _aggregate_children(children: list[TopicNode]) -> tuple[int, int, ResolutionBreakdown]:
    return (
        sum(c.document_count for c in children),
        sum(c.conversation_count for c in children),
        ResolutionBreakdown(
            resolved=sum(c.resolution_breakdown.resolved for c in children),
            partial=sum(c.resolution_breakdown.partial for c in children),
            unresolved=sum(c.resolution_breakdown.unresolved for c in children),
            unknown=sum(c.resolution_breakdown.unknown for c in children),
        ),
    )


def _build_topic_node(
    topic: Topic | None,
    by_parent: dict[int | None, list[Topic]],
    doc_counts: dict[int, int],
    breakdowns: dict[int, ResolutionBreakdown],
) -> TopicNode:
    parent_key = topic.id if topic is not None else None
    children = [_build_topic_node(c, by_parent, doc_counts, breakdowns) for c in by_parent.get(parent_key, [])]

    if topic is None:
        document_count, conversation_count, resolution_breakdown = _aggregate_children(children)
        return TopicNode(
            id=None,
            name="root",
            type="node",
            document_count=document_count,
            conversation_count=conversation_count,
            resolution_breakdown=resolution_breakdown,
            children=children,
        )

    if topic.type == TopicType.LEAF:
        breakdown = breakdowns.get(topic.id, ResolutionBreakdown())
        conversation_count = breakdown.resolved + breakdown.partial + breakdown.unresolved + breakdown.unknown
        return TopicNode(
            id=topic.id,
            name=topic.name,
            type="leaf",
            document_count=doc_counts.get(topic.id, 0),
            conversation_count=conversation_count,
            resolution_breakdown=breakdown,
            children=[],
        )

    document_count, conversation_count, resolution_breakdown = _aggregate_children(children)
    return TopicNode(
        id=topic.id,
        name=topic.name,
        type="node",
        document_count=document_count,
        conversation_count=conversation_count,
        resolution_breakdown=resolution_breakdown,
        children=children,
    )


@router.get("/tree", response_model=TopicNode)
async def get_tree(
    session: db_session_dep,
    date_from: Annotated[datetime.datetime | None, Query(alias="from")] = None,
    date_to: Annotated[datetime.datetime | None, Query(alias="to")] = None,
    source: Annotated[str | None, Query(description="Filter by conversation channel")] = None,
):
    """Get the topic tree with conversation/document counts and resolution breakdown per leaf.

    Without `from`/`to`/`source`, returns the full tree (topics with zero conversations
    included). With any of them set, the tree is pruned down to only the topics (and their
    ancestor nodes) that had at least one matching conversation.
    """
    scoped = date_from is not None or date_to is not None or source is not None
    by_parent = await topics_by_parent(session)
    doc_counts, breakdowns = await _leaf_stats(session, date_from, date_to, source)
    tree = _build_topic_node(None, by_parent, doc_counts, breakdowns)
    if not scoped:
        return tree
    pruned = _prune_empty(tree)
    return pruned or TopicNode(id=None, name="root", type="node", children=[])


ResolutionSummaryOrderBy = Literal[
    "resolution_rate", "total_conversations", "resolved", "partial", "unresolved", "unknown"
]


@router.get("/resolution-summary", response_model=list[ResolutionSummaryRow])
async def resolution_summary(
    session: db_session_dep,
    source: Annotated[str | None, Query(description="Filter by conversation channel")] = None,
    date_from: Annotated[datetime.datetime | None, Query(alias="from")] = None,
    date_to: Annotated[datetime.datetime | None, Query(alias="to")] = None,
    order_by: ResolutionSummaryOrderBy = "resolution_rate",
    dir: Literal["asc", "desc"] = "asc",
    limit: Annotated[int | None, Query(gt=0)] = None,
):
    """Resolution ranking per leaf (worst-first by default), with a documentation-gap flag."""
    query, _ = _apply_period_and_source(
        select(ConversationTopic.topic_id, ConversationTopic.resolution, func.count()), date_from, date_to, source
    )
    query = query.group_by(ConversationTopic.topic_id, ConversationTopic.resolution)

    rows = (await session.execute(query)).all()
    breakdowns: dict[int, ResolutionBreakdown] = defaultdict(ResolutionBreakdown)
    for topic_id, resolution, count in rows:
        setattr(breakdowns[topic_id], resolution, count)

    if not breakdowns:
        return []

    topic_ids = list(breakdowns.keys())
    paths = await leaf_paths_by_id(session, topic_ids)
    documented_ids = set(
        (
            await session.execute(
                select(TopicDocument.topic_id).where(TopicDocument.topic_id.in_(topic_ids)).distinct()
            )
        ).scalars()
    )

    result_rows = []
    for topic_id, breakdown in breakdowns.items():
        total = breakdown.resolved + breakdown.partial + breakdown.unresolved + breakdown.unknown
        rate = breakdown.resolved / total if total else 0.0
        result_rows.append(
            ResolutionSummaryRow(
                topic_id=topic_id,
                leaf_path=paths.get(topic_id, ""),
                total_conversations=total,
                resolved=breakdown.resolved,
                partial=breakdown.partial,
                unresolved=breakdown.unresolved,
                unknown=breakdown.unknown,
                resolution_rate=round(rate, 4),
                has_documentation=topic_id in documented_ids,
            )
        )

    result_rows.sort(key=lambda r: getattr(r, order_by), reverse=(dir == "desc"))
    if limit:
        result_rows = result_rows[:limit]
    return result_rows


ROOT_CAUSE_SAMPLE_LIMIT = 40


@router.get("/{topic_id}/root-cause", response_model=RootCauseResult)
async def root_cause(
    topic_id: int,
    session: db_session_dep,
    llm_client: llm_client_dep,
    settings: settings_dep,
    resolution: Literal["partial", "unresolved"],
    source: Annotated[str | None, Query(description="Filter by conversation channel")] = None,
    date_from: Annotated[datetime.datetime | None, Query(alias="from")] = None,
    date_to: Annotated[datetime.datetime | None, Query(alias="to")] = None,
):
    """Synthesize why most of a topic's conversations end up "partial"/"unresolved".

    Feeds the per-conversation `reasoning` already written by the classifier (not full
    transcripts) into one extra LLM call, so it stays cheap regardless of how many
    conversations matched.
    """
    topic = await session.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")

    leaf_ids = await leaf_ids_under(session, topic_id)
    if not leaf_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic has no conversations")

    query, _ = _apply_period_and_source(
        select(ConversationTopic.reasoning, ConversationTopic.created_at).where(
            ConversationTopic.topic_id.in_(leaf_ids), ConversationTopic.resolution == resolution
        ),
        date_from,
        date_to,
        source,
    )
    query = query.order_by(ConversationTopic.created_at.desc())
    rows = (await session.execute(query)).all()
    total_matching = len(rows)
    if total_matching == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No hay conversaciones con resolución '{resolution}' para este tema en el período seleccionado",
        )

    reasoning_samples = [r.reasoning for r in rows[:ROOT_CAUSE_SAMPLE_LIMIT] if r.reasoning]
    paths = await leaf_paths_by_id(session, [topic_id])
    topic_path = paths.get(topic_id, topic.name)

    system_prompt = await llm_module.get_prompt(session, llm_module.PROMPT_KEY_ROOT_CAUSE)
    analysis = await asyncio.to_thread(
        llm_module.summarize_root_cause,
        llm_client,
        settings.bedrock,
        topic_path,
        resolution,
        reasoning_samples,
        system_prompt,
    )

    return RootCauseResult(
        topic_id=topic_id,
        leaf_path=topic_path,
        resolution=resolution,
        total_matching=total_matching,
        sample_size=len(reasoning_samples),
        main_cause=analysis.get("main_cause", ""),
        explanation=analysis.get("explanation", ""),
        secondary_causes=analysis.get("secondary_causes", []),
    )


async def _build_activity_heatmap(
    session: AsyncSession,
    leaf_ids: list[int],
    topic_id: int | None,
    leaf_path: str,
    source: str | None,
    date_from: datetime.datetime | None,
    date_to: datetime.datetime | None,
) -> ActivityHeatmapResult | None:
    """Shared core for both the per-topic and whole-tree activity-heatmap endpoints.

    "Average" is per calendar occurrence of that weekday within the period — a weekday with
    zero conversations still counts in the denominator, so a quiet Sunday pulls the average
    down instead of just being absent from the data. Returns None if there's nothing to show
    (no leaves, or no processed conversations at all to derive a default period from).
    """
    if not leaf_ids:
        return None

    effective_from, effective_to = date_from, date_to
    if effective_from is None or effective_to is None:
        bounds = (
            await session.execute(
                select(
                    func.min(ProcessedConversation.source_created_at), func.max(ProcessedConversation.source_created_at)
                )
            )
        ).one()
        effective_from = effective_from or bounds[0]
        effective_to = effective_to or bounds[1]
    if effective_from is None or effective_to is None:
        return None

    query = (
        select(ConversationTopic.conversation_id, ProcessedConversation.source_created_at)
        .join(ProcessedConversation, ProcessedConversation.conversation_id == ConversationTopic.conversation_id)
        .where(ConversationTopic.topic_id.in_(leaf_ids))
        .where(ProcessedConversation.source_created_at >= effective_from)
        .where(ProcessedConversation.source_created_at <= effective_to)
        .distinct()
    )
    if source is not None:
        query = query.where(ProcessedConversation.source == source)
    rows = (await session.execute(query)).all()

    cell_counts: dict[tuple[int, int], int] = defaultdict(int)
    for _, created_at in rows:
        local = created_at.astimezone(LOCAL_TZ)
        cell_counts[(local.weekday(), local.hour)] += 1

    weekday_occurrences = [0] * 7
    day = effective_from.astimezone(LOCAL_TZ).date()
    last_day = effective_to.astimezone(LOCAL_TZ).date()
    while day <= last_day:
        weekday_occurrences[day.weekday()] += 1
        day += datetime.timedelta(days=1)

    cells = [
        ActivityHeatmapCell(
            day_of_week=dow,
            hour=hour,
            total=cell_counts.get((dow, hour), 0),
            average=(cell_counts.get((dow, hour), 0) / weekday_occurrences[dow]) if weekday_occurrences[dow] else 0.0,
        )
        for dow in range(7)
        for hour in range(24)
    ]

    return ActivityHeatmapResult(
        topic_id=topic_id,
        leaf_path=leaf_path,
        total_conversations=len(rows),
        cells=cells,
    )


@router.get("/{topic_id}/activity-heatmap", response_model=ActivityHeatmapResult)
async def activity_heatmap(
    topic_id: int,
    session: db_session_dep,
    source: Annotated[str | None, Query(description="Filter by conversation channel")] = None,
    date_from: Annotated[datetime.datetime | None, Query(alias="from")] = None,
    date_to: Annotated[datetime.datetime | None, Query(alias="to")] = None,
):
    """Average conversation volume by hour-of-day and day-of-week (local Buenos Aires time), for one topic."""
    topic = await session.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")

    leaf_ids = await leaf_ids_under(session, topic_id)
    paths = await leaf_paths_by_id(session, [topic_id])
    result = await _build_activity_heatmap(
        session, leaf_ids, topic_id, paths.get(topic_id, topic.name), source, date_from, date_to
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic has no conversations")
    return result


@router.get("/activity-heatmap", response_model=ActivityHeatmapResult)
async def whole_tree_activity_heatmap(
    session: db_session_dep,
    source: Annotated[str | None, Query(description="Filter by conversation channel")] = None,
    date_from: Annotated[datetime.datetime | None, Query(alias="from")] = None,
    date_to: Annotated[datetime.datetime | None, Query(alias="to")] = None,
):
    """Average conversation volume by hour-of-day and day-of-week, across every topic (the root)."""
    leaf_ids = (await session.execute(select(Topic.id).where(Topic.type == TopicType.LEAF))).scalars().all()
    result = await _build_activity_heatmap(session, list(leaf_ids), None, "Todos los temas", source, date_from, date_to)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No processed conversations yet")
    return result


@router.get("/{topic_id}/documents", response_model=list[DocumentOut])
async def list_topic_documents(topic_id: int, session: db_session_dep):
    """List documents assigned under a topic.

    A leaf's own documents, or every document assigned anywhere in a node's subtree (deduped).
    """
    topic = await session.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
    leaf_ids = await leaf_ids_under(session, topic_id)
    if not leaf_ids:
        return []
    return (
        (
            await session.execute(
                select(Document)
                .join(TopicDocument, TopicDocument.document_id == Document.id)
                .where(TopicDocument.topic_id.in_(leaf_ids))
                .distinct()
                .order_by(Document.name)
            )
        )
        .scalars()
        .all()
    )


@router.delete(
    "/{topic_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_editor)],
)
async def unassign_document(
    topic_id: int, document_id: int, request: Request, session: db_session_dep, actor: current_user_dep
):
    """Unassign a document from a leaf, without deleting the document or the leaf."""
    result = await session.execute(
        delete(TopicDocument).where(TopicDocument.topic_id == topic_id, TopicDocument.document_id == document_id)
    )
    if result.rowcount == 0:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    await log_action(
        session,
        actor.username,
        actor.role,
        ACTION_TOPIC_DOCUMENT_UNASSIGN,
        detail=f"topic={topic_id} document={document_id}",
        request=request,
    )


@router.get("/{topic_id}/conversations", response_model=ConversationTopicPage)
async def list_topic_conversations(
    topic_id: int,
    session: db_session_dep,
    source: Annotated[str | None, Query(description="Filter by conversation channel")] = None,
    date_from: Annotated[datetime.datetime | None, Query(alias="from")] = None,
    date_to: Annotated[datetime.datetime | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(gt=0, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Page through conversations assigned under a topic, most recent first.

    A leaf's own conversations, or every conversation assigned anywhere in a node's
    subtree. Returns a `total` count alongside the page so the front can paginate
    without ever having to load the full list, however large it gets.
    """
    topic = await session.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
    leaf_ids = await leaf_ids_under(session, topic_id)
    if not leaf_ids:
        return ConversationTopicPage(total=0, items=[])

    base_where = ConversationTopic.topic_id.in_(leaf_ids)

    total_query, _ = _apply_period_and_source(
        select(func.count()).select_from(ConversationTopic).where(base_where), date_from, date_to, source
    )
    total = (await session.execute(total_query)).scalar_one()

    items_query, _ = _apply_period_and_source(select(ConversationTopic).where(base_where), date_from, date_to, source)
    items_query = items_query.order_by(ConversationTopic.created_at.desc()).limit(limit).offset(offset)
    items = (await session.execute(items_query)).scalars().all()
    return ConversationTopicPage(total=total, items=items)


@router.post("", response_model=TopicOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_editor)])
async def create_topic(payload: TopicCreateIn, request: Request, session: db_session_dep, actor: current_user_dep):
    """Manually create a node or leaf (not via LLM classification), attached under `parent_id`."""
    if payload.parent_id is not None:
        parent = await session.get(Topic, payload.parent_id)
        if parent is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent topic not found")
        if parent.type != TopicType.NODE:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Parent must be a node, not a leaf")

    topic = Topic(parent_id=payload.parent_id, name=payload.name, type=TopicType(payload.type))
    session.add(topic)
    try:
        await session.flush()
    except IntegrityError as e:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A topic with that name already exists there"
        ) from e

    await log_action(
        session,
        actor.username,
        actor.role,
        ACTION_TOPIC_CREATE,
        detail=f"{payload.type} '{payload.name}'",
        request=request,
    )
    await session.refresh(topic)
    return topic


@router.patch("/{topic_id}", response_model=TopicOut, dependencies=[Depends(require_editor)])
async def rename_topic(
    topic_id: int, payload: TopicRenameIn, request: Request, session: db_session_dep, actor: current_user_dep
):
    """Rename an existing node or leaf."""
    topic = await session.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")

    old_name = topic.name
    topic.name = payload.name
    try:
        await session.flush()
    except IntegrityError as e:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A topic with that name already exists there"
        ) from e

    await log_action(
        session,
        actor.username,
        actor.role,
        ACTION_TOPIC_RENAME,
        detail=f"'{old_name}' -> '{payload.name}'",
        request=request,
    )
    await session.refresh(topic)
    return topic


@router.patch("/{topic_id}/move", response_model=TopicOut, dependencies=[Depends(require_editor)])
async def move_topic(
    topic_id: int, payload: TopicMoveIn, request: Request, session: db_session_dep, actor: current_user_dep
):
    """Re-parent a node or leaf (drag & drop), without touching its name or contents."""
    topic = await session.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")

    if payload.parent_id is not None:
        if payload.parent_id == topic_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A topic can't be its own parent")
        new_parent = await session.get(Topic, payload.parent_id)
        if new_parent is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="New parent not found")
        if new_parent.type != TopicType.NODE:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="New parent must be a node, not a leaf")
        if topic.type == TopicType.NODE and await is_within_subtree(session, topic_id, payload.parent_id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Can't move a node under its own subtree")

    old_parent_id = topic.parent_id
    topic.parent_id = payload.parent_id
    try:
        await session.flush()
    except IntegrityError as e:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A topic with that name already exists there"
        ) from e

    await log_action(
        session,
        actor.username,
        actor.role,
        ACTION_TOPIC_MOVE,
        detail=f"'{topic.name}' parent {old_parent_id} -> {payload.parent_id}",
        request=request,
    )
    await session.refresh(topic)
    return topic


@router.delete("/{topic_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_editor)])
async def delete_topic(topic_id: int, request: Request, session: db_session_dep, actor: current_user_dep):
    """Delete an empty node, or a leaf with no documents/conversations assigned.

    Refuses (409) otherwise, so deleting never silently orphans classified data — unassign
    documents and let conversations naturally move on before deleting a leaf.
    """
    topic = await session.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")

    if topic.type == TopicType.NODE:
        has_children = (
            await session.execute(select(Topic.id).where(Topic.parent_id == topic_id).limit(1))
        ).scalar_one_or_none()
        if has_children is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Node has children — move or delete them first"
            )
    else:
        has_docs = (
            await session.execute(select(TopicDocument.topic_id).where(TopicDocument.topic_id == topic_id).limit(1))
        ).scalar_one_or_none()
        has_convs = (
            await session.execute(select(ConversationTopic.id).where(ConversationTopic.topic_id == topic_id).limit(1))
        ).scalar_one_or_none()
        if has_docs is not None or has_convs is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Leaf has documents or conversations assigned — unassign them first",
            )

    name = topic.name
    await session.delete(topic)
    await log_action(session, actor.username, actor.role, ACTION_TOPIC_DELETE, detail=name, request=request)


@router.post("/restructure", response_model=RestructureResult, dependencies=[Depends(require_editor)])
async def restructure(
    payload: RestructureRequest,
    request: Request,
    session: db_session_dep,
    llm_client: llm_client_dep,
    settings: settings_dep,
    actor: current_user_dep,
):
    """Reorganize the node hierarchy (never touches leaves), optionally guided by an instruction."""
    structure = await load_tree_structure_from_db(session)
    system_prompt = await llm_module.get_prompt(session, llm_module.PROMPT_KEY_RESTRUCTURE)
    new_structure = await asyncio.to_thread(
        llm_module.restructure_tree, llm_client, settings.bedrock, structure, payload.instruction, system_prompt
    )
    try:
        kept = await apply_restructure(session, new_structure)
    except TreeRestructureError as e:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    await log_action(
        session, actor.username, actor.role, ACTION_TOPIC_RESTRUCTURE, detail=payload.instruction, request=request
    )
    return RestructureResult(leaves_kept=kept)
