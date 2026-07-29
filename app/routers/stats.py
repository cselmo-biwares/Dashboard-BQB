"""Dashboard KPI/trend routes, shaped for the front so it doesn't need to aggregate client-side.

Bucketing for the trend is done in Python (not SQL date_trunc) so the aggregation stays
portable/testable and doesn't tie the query to a specific DB dialect. At this data volume
(customer support conversations) that's cheap enough to not warrant precomputing.
"""

import datetime
from collections import defaultdict
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Select, func, select

from app.db.models import ConversationTopic, ProcessedConversation
from app.dependencies.auth import require_any_role
from app.dependencies.db import db_session_dep
from app.schemas.stats import SourceBreakdownRow, StatsOverview, VolumeTrendPoint

router = APIRouter(prefix="/stats", tags=["stats"], dependencies=[Depends(require_any_role)])


def _apply_period_filters(
    query: Select, source: str | None, date_from: datetime.datetime | None, date_to: datetime.datetime | None
) -> Select:
    if source:
        query = query.where(ProcessedConversation.source == source)
    if date_from:
        query = query.where(ProcessedConversation.source_created_at >= date_from)
    if date_to:
        query = query.where(ProcessedConversation.source_created_at <= date_to)
    return query


@router.get("/overview", response_model=StatsOverview)
async def get_overview(
    session: db_session_dep,
    source: Annotated[str | None, Query(description="Filter by conversation channel")] = None,
    date_from: Annotated[datetime.datetime | None, Query(alias="from")] = None,
    date_to: Annotated[datetime.datetime | None, Query(alias="to")] = None,
):
    """Totals for a period: conversations processed + resolution breakdown across all topics."""
    conv_query = _apply_period_filters(
        select(func.count(ProcessedConversation.conversation_id)), source, date_from, date_to
    )
    total_conversations = (await session.execute(conv_query)).scalar_one()

    breakdown_query = _apply_period_filters(
        select(ConversationTopic.resolution, func.count())
        .join(ProcessedConversation, ProcessedConversation.conversation_id == ConversationTopic.conversation_id)
        .group_by(ConversationTopic.resolution),
        source,
        date_from,
        date_to,
    )
    counts = dict((await session.execute(breakdown_query)).all())
    resolved, partial, unresolved, unknown = (
        counts.get("resolved", 0),
        counts.get("partial", 0),
        counts.get("unresolved", 0),
        counts.get("unknown", 0),
    )
    total_mentions = resolved + partial + unresolved + unknown
    rate = resolved / total_mentions if total_mentions else 0.0

    return StatsOverview(
        total_conversations=total_conversations,
        resolved=resolved,
        partial=partial,
        unresolved=unresolved,
        unknown=unknown,
        overall_resolution_rate=round(rate, 4),
    )


IntervalLiteral = Literal["day", "week", "month"]


def _bucket_start(dt: datetime.datetime, interval: IntervalLiteral) -> datetime.datetime:
    bucket = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    if interval == "week":
        bucket -= datetime.timedelta(days=bucket.weekday())
    elif interval == "month":
        bucket = bucket.replace(day=1)
    return bucket


@router.get("/volume-trend", response_model=list[VolumeTrendPoint])
async def get_volume_trend(
    session: db_session_dep,
    source: Annotated[str | None, Query(description="Filter by conversation channel")] = None,
    interval: IntervalLiteral = "day",
    date_from: Annotated[datetime.datetime | None, Query(alias="from")] = None,
    date_to: Annotated[datetime.datetime | None, Query(alias="to")] = None,
):
    """Conversation volume + resolution breakdown per day/week bucket."""
    conv_query = _apply_period_filters(
        select(ProcessedConversation.conversation_id, ProcessedConversation.source_created_at),
        source,
        date_from,
        date_to,
    )
    conv_dates: dict[int, datetime.datetime] = dict((await session.execute(conv_query)).all())

    topic_query = _apply_period_filters(
        select(ConversationTopic.conversation_id, ConversationTopic.resolution).join(
            ProcessedConversation, ProcessedConversation.conversation_id == ConversationTopic.conversation_id
        ),
        source,
        date_from,
        date_to,
    )
    topic_rows = (await session.execute(topic_query)).all()

    totals: dict[datetime.datetime, int] = defaultdict(int)
    for created_at in conv_dates.values():
        totals[_bucket_start(created_at, interval)] += 1

    breakdowns: dict[datetime.datetime, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for conversation_id, resolution in topic_rows:
        created_at = conv_dates.get(conversation_id)
        if created_at is None:
            continue
        breakdowns[_bucket_start(created_at, interval)][resolution] += 1

    points = []
    for period_start in sorted(totals.keys()):
        breakdown = breakdowns.get(period_start, {})
        points.append(
            VolumeTrendPoint(
                period_start=period_start,
                total_conversations=totals[period_start],
                resolved=breakdown.get("resolved", 0),
                partial=breakdown.get("partial", 0),
                unresolved=breakdown.get("unresolved", 0),
                unknown=breakdown.get("unknown", 0),
            )
        )
    return points


@router.get("/by-source", response_model=list[SourceBreakdownRow])
async def get_by_source(
    session: db_session_dep,
    date_from: Annotated[datetime.datetime | None, Query(alias="from")] = None,
    date_to: Annotated[datetime.datetime | None, Query(alias="to")] = None,
):
    """Per-channel totals + resolution breakdown for a period, sorted by volume (desc)."""
    conv_query = _apply_period_filters(
        select(ProcessedConversation.source, func.count(ProcessedConversation.conversation_id)).group_by(
            ProcessedConversation.source
        ),
        None,
        date_from,
        date_to,
    )
    totals = dict((await session.execute(conv_query)).all())

    breakdown_query = _apply_period_filters(
        select(ProcessedConversation.source, ConversationTopic.resolution, func.count())
        .join(ProcessedConversation, ProcessedConversation.conversation_id == ConversationTopic.conversation_id)
        .group_by(ProcessedConversation.source, ConversationTopic.resolution),
        None,
        date_from,
        date_to,
    )
    breakdowns: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for source, resolution, count in await session.execute(breakdown_query):
        breakdowns[source][resolution] = count

    rows = []
    for source, total in totals.items():
        breakdown = breakdowns.get(source, {})
        resolved, partial, unresolved, unknown = (
            breakdown.get("resolved", 0),
            breakdown.get("partial", 0),
            breakdown.get("unresolved", 0),
            breakdown.get("unknown", 0),
        )
        mentions = resolved + partial + unresolved + unknown
        rate = resolved / mentions if mentions else 0.0
        rows.append(
            SourceBreakdownRow(
                source=source,
                total_conversations=total,
                resolved=resolved,
                partial=partial,
                unresolved=unresolved,
                unknown=unknown,
                overall_resolution_rate=round(rate, 4),
            )
        )
    rows.sort(key=lambda r: r.total_conversations, reverse=True)
    return rows
