"""Loading, classification and restructuring of the topic tree against the destination DB.

Two distinct operations (see the plan):
- classification (`apply_document_classification` / `apply_conversation_classification`) is
  always append-only: it may create new leaves, but never touches existing nodes/leaves.
- restructuring (`apply_restructure`) only reshuffles nodes; the set of leaf names must stay
  exactly the same before and after, so document/conversation assignments (by leaf id) are
  never affected.
"""

import logging
from collections import defaultdict

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ConversationTopic, Document, Topic, TopicDocument, TopicType

logger = logging.getLogger(__name__)


class TreeRestructureError(Exception):
    """Raised when a restructure result would change the set of leaves."""

    def __init__(self, missing: set[str], extra: set[str], duplicated: set[str]):
        """Initialize with the leaf-set discrepancies that caused the rejection."""
        self.missing = missing
        self.extra = extra
        self.duplicated = duplicated
        super().__init__(f"Leaf set changed: missing={missing} extra={extra} duplicated={duplicated}")


async def topics_by_parent(session: AsyncSession) -> dict[int | None, list[Topic]]:
    """Load all topics grouped by parent_id (None = children of the synthetic root)."""
    topics = (await session.execute(select(Topic))).scalars().all()
    by_parent: dict[int | None, list[Topic]] = defaultdict(list)
    for topic in topics:
        by_parent[topic.parent_id].append(topic)
    return by_parent


async def leaf_paths_by_id(session: AsyncSession, topic_ids: list[int]) -> dict[int, str]:
    """Resolve a set of topic ids to their full 'A > B > C' path (without the root)."""
    all_topics = (await session.execute(select(Topic.id, Topic.parent_id, Topic.name))).all()
    by_id = {t.id: t for t in all_topics}
    paths: dict[int, str] = {}
    for topic_id in topic_ids:
        names: list[str] = []
        current = by_id.get(topic_id)
        while current is not None:
            names.append(current.name)
            current = by_id.get(current.parent_id) if current.parent_id is not None else None
        paths[topic_id] = " > ".join(reversed(names))
    return paths


async def leaf_ids_under(session: AsyncSession, topic_id: int) -> list[int]:
    """Get all leaf ids under a topic.

    Itself if it's already a leaf, otherwise every leaf in its subtree. Used to
    aggregate documents/conversations at any node, not just at leaves.
    """
    by_parent = await topics_by_parent(session)
    by_id = {t.id: t for topics in by_parent.values() for t in topics}
    root = by_id.get(topic_id)
    if root is None:
        return []
    if root.type == TopicType.LEAF:
        return [topic_id]

    leaf_ids: list[int] = []

    def _walk(node_id: int) -> None:
        for child in by_parent.get(node_id, []):
            if child.type == TopicType.LEAF:
                leaf_ids.append(child.id)
            else:
                _walk(child.id)

    _walk(topic_id)
    return leaf_ids


async def is_within_subtree(session: AsyncSession, root_id: int, candidate_id: int) -> bool:
    """Check whether `candidate_id` is `root_id` itself or one of its descendants.

    Used to reject a manual move that would re-parent a node under its own subtree (a cycle).
    """
    if root_id == candidate_id:
        return True
    by_parent = await topics_by_parent(session)

    def _walk(node_id: int) -> bool:
        for child in by_parent.get(node_id, []):
            if child.id == candidate_id or _walk(child.id):
                return True
        return False

    return _walk(root_id)


async def _documents_by_leaf(session: AsyncSession, leaf_ids: list[int]) -> dict[int, list[str]]:
    if not leaf_ids:
        return {}
    rows = (
        await session.execute(
            select(TopicDocument.topic_id, Document.name)
            .join(Document, Document.id == TopicDocument.document_id)
            .where(TopicDocument.topic_id.in_(leaf_ids))
        )
    ).all()
    by_leaf: dict[int, list[str]] = defaultdict(list)
    for topic_id, name in rows:
        by_leaf[topic_id].append(name)
    return by_leaf


def _build_tree(by_parent: dict[int | None, list[Topic]], docs_by_leaf: dict[int, list[str]] | None) -> dict:
    def _build(topic: Topic | None) -> dict:
        if topic is None:
            return {"name": "root", "children": [_build(c) for c in by_parent.get(None, [])]}
        node: dict = {"name": topic.name, "type": topic.type.value}
        if topic.type == TopicType.LEAF:
            if docs_by_leaf is not None:
                node["documents"] = docs_by_leaf.get(topic.id, [])
        else:
            node["children"] = [_build(c) for c in by_parent.get(topic.id, [])]
        return node

    return _build(None)


async def load_full_tree_from_db(session: AsyncSession) -> dict:
    """Load the tree as nested JSON with documents assigned per leaf, for classification prompts."""
    by_parent = await topics_by_parent(session)
    leaf_ids = [t.id for topics in by_parent.values() for t in topics if t.type == TopicType.LEAF]
    docs_by_leaf = await _documents_by_leaf(session, leaf_ids)
    return _build_tree(by_parent, docs_by_leaf)


async def load_tree_structure_from_db(session: AsyncSession) -> dict:
    """Load just the shape of the tree (node/leaf names and hierarchy), for the restructure prompt."""
    by_parent = await topics_by_parent(session)
    return _build_tree(by_parent, docs_by_leaf=None)


async def _resolve_topic_by_path(session: AsyncSession, path: str) -> Topic | None:
    """Resolve a non-empty 'A > B > C' path to its Topic row (None if any segment is missing)."""
    parent_id: int | None = None
    topic: Topic | None = None
    for part in path.split(" > "):
        result = await session.execute(select(Topic).where(Topic.parent_id == parent_id, Topic.name == part))
        topic = result.scalar_one_or_none()
        if topic is None:
            return None
        parent_id = topic.id
    return topic


async def _ensure_leaf(session: AsyncSession, parent_path: str, name: str) -> Topic:
    """Get or create a leaf under parent_path (empty parent_path = directly under root)."""
    parent_id: int | None = None
    if parent_path:
        parent = await _resolve_topic_by_path(session, parent_path)
        if parent is None:
            logger.warning("Parent path '%s' not found, attaching new leaf '%s' under root", parent_path, name)
        else:
            parent_id = parent.id

    existing = (
        await session.execute(select(Topic).where(Topic.parent_id == parent_id, Topic.name == name))
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    leaf = Topic(parent_id=parent_id, name=name, type=TopicType.LEAF)
    session.add(leaf)
    await session.flush()
    return leaf


async def apply_document_classification(session: AsyncSession, document_id: int, classification: dict) -> list[str]:
    """Apply a document classification result: create missing leaves, assign the document.

    :return: the leaf paths the document ended up assigned to
    """
    for new_leaf in classification.get("new_leaves", []):
        await _ensure_leaf(session, new_leaf["parent_path"], new_leaf["name"])

    assigned_paths = []
    for leaf_path in classification.get("leaf_paths", []):
        leaf = await _resolve_topic_by_path(session, leaf_path)
        if leaf is None or leaf.type != TopicType.LEAF:
            logger.warning("Document classification: leaf path '%s' not found, skipping", leaf_path)
            continue
        existing = (
            await session.execute(
                select(TopicDocument).where(TopicDocument.topic_id == leaf.id, TopicDocument.document_id == document_id)
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(TopicDocument(topic_id=leaf.id, document_id=document_id))
        assigned_paths.append(leaf_path)
    return assigned_paths


async def apply_conversation_classification(
    session: AsyncSession, conversation_id: int, classification: dict
) -> list[ConversationTopic]:
    """Apply a conversation classification result: create missing leaves, assign topics + resolution."""
    for new_leaf in classification.get("new_leaves", []):
        await _ensure_leaf(session, new_leaf["parent_path"], new_leaf["name"])

    assigned: list[ConversationTopic] = []
    for topic_entry in classification.get("topics", []):
        leaf_path = topic_entry["leaf_path"]
        leaf = await _resolve_topic_by_path(session, leaf_path)
        if leaf is None or leaf.type != TopicType.LEAF:
            logger.warning("Conversation classification: leaf path '%s' not found, skipping", leaf_path)
            continue

        resolution = topic_entry.get("resolution", "unknown")
        reasoning = topic_entry.get("reasoning", "")
        row = (
            await session.execute(
                select(ConversationTopic).where(
                    ConversationTopic.conversation_id == conversation_id, ConversationTopic.topic_id == leaf.id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = ConversationTopic(
                conversation_id=conversation_id, topic_id=leaf.id, resolution=resolution, reasoning=reasoning
            )
            session.add(row)
        else:
            row.resolution = resolution
            row.reasoning = reasoning
        assigned.append(row)
    return assigned


def _collect_leaf_names(structure: dict) -> list[str]:
    names: list[str] = []

    def _walk(node: dict) -> None:
        if node.get("type") == "leaf":
            names.append(node["name"])
        for child in node.get("children", []):
            _walk(child)

    for child in structure.get("children", []):
        _walk(child)
    return names


async def apply_restructure(session: AsyncSession, new_structure: dict) -> int:
    """Reorganize the node hierarchy from an LLM restructure result, re-parenting leaves by name.

    Validates that the leaf set (by name) is unchanged before applying anything; raises
    TreeRestructureError otherwise, without touching the database.

    :return: number of leaves kept
    """
    current_leaves = (await session.execute(select(Topic).where(Topic.type == TopicType.LEAF))).scalars().all()
    current_names = {t.name for t in current_leaves}
    leaf_by_name = {t.name: t for t in current_leaves}

    new_names = _collect_leaf_names(new_structure)
    new_names_set = set(new_names)
    duplicated = {n for n in new_names_set if new_names.count(n) > 1}
    missing = current_names - new_names_set
    extra = new_names_set - current_names
    if missing or extra or duplicated:
        raise TreeRestructureError(missing=missing, extra=extra, duplicated=duplicated)

    # Detach leaves before deleting nodes, so the ON DELETE CASCADE on topic.parent_id
    # doesn't take the leaves down with their (soon to be replaced) parent nodes.
    for leaf in current_leaves:
        leaf.parent_id = None
    await session.flush()

    await session.execute(delete(Topic).where(Topic.type == TopicType.NODE))
    await session.flush()

    async def _create(node: dict, parent_id: int | None) -> None:
        if node.get("type") == "leaf":
            leaf_by_name[node["name"]].parent_id = parent_id
            return
        new_node = Topic(name=node["name"], type=TopicType.NODE, parent_id=parent_id)
        session.add(new_node)
        await session.flush()
        for child in node.get("children", []):
            await _create(child, new_node.id)

    for child in new_structure.get("children", []):
        await _create(child, None)
    await session.flush()

    return len(current_names)
