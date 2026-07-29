"""Analyst notes: freeform notes shared across all roles, optionally saved from a root-cause analysis.

Any authenticated user can edit or delete any note (not just their own) — this is meant as a
shared, collaborative log, not a per-user scratchpad. `created_by`/`updated_by` keep it
traceable without restricting who can act on it.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select

from app.audit import ACTION_NOTE_CREATE, ACTION_NOTE_DELETE, ACTION_NOTE_UPDATE, log_action
from app.db.models import AnalystNote, Topic
from app.dependencies.auth import current_user_dep, require_any_role
from app.dependencies.db import db_session_dep
from app.ingestion.tree import leaf_paths_by_id
from app.schemas.notes import NoteIn, NoteOut, NoteUpdateIn

router = APIRouter(prefix="/notes", tags=["notes"], dependencies=[Depends(require_any_role)])


@router.get("", response_model=list[NoteOut])
async def list_notes(session: db_session_dep, topic_id: int | None = None):
    """List notes, newest first, optionally filtered to one topic."""
    stmt = select(AnalystNote).order_by(AnalystNote.created_at.desc())
    if topic_id is not None:
        stmt = stmt.where(AnalystNote.topic_id == topic_id)
    return (await session.execute(stmt)).scalars().all()


@router.post("", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
async def create_note(payload: NoteIn, request: Request, session: db_session_dep, actor: current_user_dep):
    """Create a note, standalone or linked to a topic (e.g. from a root-cause analysis)."""
    leaf_path = payload.leaf_path
    if payload.topic_id is not None:
        topic = await session.get(Topic, payload.topic_id)
        if topic is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
        if leaf_path is None:
            leaf_path = (await leaf_paths_by_id(session, [payload.topic_id])).get(payload.topic_id, topic.name)

    note = AnalystNote(
        title=payload.title,
        content=payload.content,
        topic_id=payload.topic_id,
        leaf_path=leaf_path,
        resolution=payload.resolution,
        filter_source=payload.filter_source,
        filter_from=payload.filter_from,
        filter_to=payload.filter_to,
        created_by=actor.username,
        updated_by=actor.username,
    )
    session.add(note)
    await log_action(session, actor.username, actor.role, ACTION_NOTE_CREATE, detail=payload.title, request=request)
    await session.refresh(note)
    return note


@router.put("/{note_id}", response_model=NoteOut)
async def update_note(
    note_id: int, payload: NoteUpdateIn, request: Request, session: db_session_dep, actor: current_user_dep
):
    """Edit a note's title/content. Its topic/resolution context is fixed at creation."""
    note = await session.get(AnalystNote, note_id)
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")

    note.title = payload.title
    note.content = payload.content
    note.updated_by = actor.username
    await log_action(session, actor.username, actor.role, ACTION_NOTE_UPDATE, detail=note.title, request=request)
    await session.refresh(note)
    return note


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(note_id: int, request: Request, session: db_session_dep, actor: current_user_dep):
    """Delete a note."""
    note = await session.get(AnalystNote, note_id)
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")

    title = note.title
    await session.delete(note)
    await log_action(session, actor.username, actor.role, ACTION_NOTE_DELETE, detail=title, request=request)
