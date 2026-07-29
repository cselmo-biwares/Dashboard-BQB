"""Routes for the three front-editable LLM system prompts.

Edits are read fresh on every LLM call (see app.ingestion.llm.get_prompt), so they take
effect on the next call — no restart needed.
"""

from fastapi import APIRouter, Depends, Request

from app.audit import ACTION_PROMPT_RESET, ACTION_PROMPT_UPDATE, log_action
from app.db.models import PromptOverride
from app.dependencies.auth import current_user_dep, require_editor
from app.dependencies.db import db_session_dep
from app.ingestion.llm import DEFAULT_PROMPTS
from app.schemas.prompts import PromptKeyLiteral, PromptOut, PromptUpdateIn

router = APIRouter(prefix="/prompts", tags=["prompts"], dependencies=[Depends(require_editor)])


def _to_out(key: str, override: PromptOverride | None) -> PromptOut:
    if override is None:
        return PromptOut(key=key, content=DEFAULT_PROMPTS[key], is_default=True, updated_at=None)
    return PromptOut(key=key, content=override.content, is_default=False, updated_at=override.updated_at)


@router.get("", response_model=list[PromptOut])
async def list_prompts(session: db_session_dep):
    """Get the current value of all three system prompts."""
    result = []
    for key in DEFAULT_PROMPTS:
        override = await session.get(PromptOverride, key)
        result.append(_to_out(key, override))
    return result


@router.get("/{key}", response_model=PromptOut)
async def get_prompt_route(key: PromptKeyLiteral, session: db_session_dep):
    """Get the current value of one system prompt."""
    override = await session.get(PromptOverride, key)
    return _to_out(key, override)


@router.put("/{key}", response_model=PromptOut)
async def update_prompt(
    key: PromptKeyLiteral, payload: PromptUpdateIn, request: Request, session: db_session_dep, actor: current_user_dep
):
    """Set an override for a system prompt. Takes effect on the next LLM call."""
    override = await session.get(PromptOverride, key)
    if override is None:
        override = PromptOverride(key=key, content=payload.content)
        session.add(override)
    else:
        override.content = payload.content
    await log_action(session, actor.username, actor.role, ACTION_PROMPT_UPDATE, detail=key, request=request)
    await session.refresh(override)
    return _to_out(key, override)


@router.post("/{key}/reset", response_model=PromptOut)
async def reset_prompt(key: PromptKeyLiteral, request: Request, session: db_session_dep, actor: current_user_dep):
    """Remove the override for a system prompt, reverting it to the hardcoded default."""
    override = await session.get(PromptOverride, key)
    if override is not None:
        await session.delete(override)
        await log_action(session, actor.username, actor.role, ACTION_PROMPT_RESET, detail=key, request=request)
    return _to_out(key, None)
