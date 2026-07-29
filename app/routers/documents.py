"""Document ingestion routes: documents are sent one at a time and classified immediately."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select

from app.audit import ACTION_DOCUMENT_CREATE, ACTION_DOCUMENT_DELETE, log_action
from app.db.models import Document
from app.dependencies.auth import current_user_dep, require_editor
from app.dependencies.config import settings_dep
from app.dependencies.db import db_session_dep
from app.dependencies.llm import llm_client_dep
from app.ingestion import llm as llm_module
from app.ingestion.tree import apply_document_classification, load_full_tree_from_db
from app.schemas.documents import DocumentClassifyResult, DocumentIn, DocumentOut

router = APIRouter(prefix="/documents", tags=["documents"], dependencies=[Depends(require_editor)])


@router.post("", response_model=DocumentClassifyResult)
async def create_document(
    payload: DocumentIn,
    request: Request,
    session: db_session_dep,
    llm_client: llm_client_dep,
    settings: settings_dep,
    actor: current_user_dep,
):
    """
    Upsert a document (by name) and classify it against the existing topic tree.

    Append-only: may assign the document to existing leaves or create new ones, never
    touches existing nodes/leaves.
    """
    existing = (await session.execute(select(Document).where(Document.name == payload.name))).scalar_one_or_none()
    if existing is None:
        document = Document(name=payload.name, content=payload.content)
        session.add(document)
    else:
        document = existing
        document.content = payload.content
    await session.flush()

    tree = await load_full_tree_from_db(session)
    system_prompt = await llm_module.get_prompt(session, llm_module.PROMPT_KEY_CLASSIFY_DOCUMENT)
    classification = await asyncio.to_thread(
        llm_module.classify_document,
        llm_client,
        settings.bedrock,
        tree,
        document.name,
        document.content,
        system_prompt,
    )
    assigned_paths = await apply_document_classification(session, document.id, classification)
    await log_action(session, actor.username, actor.role, ACTION_DOCUMENT_CREATE, detail=document.name, request=request)
    await session.commit()
    await session.refresh(document)

    return DocumentClassifyResult(document=DocumentOut.model_validate(document), assigned_leaf_paths=assigned_paths)


@router.get("", response_model=list[DocumentOut])
async def list_documents(session: db_session_dep):
    """List all documents."""
    return (await session.execute(select(Document).order_by(Document.name))).scalars().all()


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: int, request: Request, session: db_session_dep, actor: current_user_dep):
    """Delete a document and all of its topic assignments."""
    document = await session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    await session.delete(document)
    await log_action(session, actor.username, actor.role, ACTION_DOCUMENT_DELETE, detail=document.name, request=request)
