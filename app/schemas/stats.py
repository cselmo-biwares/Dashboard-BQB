"""Dashboard KPI/trend schemas, aggregated in a single query for the front."""

import datetime

from pydantic import BaseModel


class StatsOverview(BaseModel):
    """Totals for a period, optionally filtered by channel."""

    total_conversations: int
    resolved: int
    partial: int
    unresolved: int
    unknown: int
    overall_resolution_rate: float


class VolumeTrendPoint(BaseModel):
    """One bucket (day/week/month) of the volume/resolution trend."""

    period_start: datetime.datetime
    total_conversations: int
    resolved: int
    partial: int
    unresolved: int
    unknown: int


class SourceBreakdownRow(BaseModel):
    """Totals for one conversation channel (source), for a period."""

    source: str
    total_conversations: int
    resolved: int
    partial: int
    unresolved: int
    unknown: int
    overall_resolution_rate: float
