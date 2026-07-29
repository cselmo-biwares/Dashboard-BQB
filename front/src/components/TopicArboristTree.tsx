import { useEffect, useRef, useState } from "react";
import { Tree } from "react-arborist";
import type { CreateHandler, DeleteHandler, MoveHandler, NodeApi, NodeRendererProps, RenameHandler, TreeApi } from "react-arborist";
import { ApiError, createTopic, deleteTopic, moveTopic, renameTopic } from "../api";
import type { ResolutionBreakdown, TopicNode } from "../types";
import { BreakdownBar } from "./BreakdownBar";

const ROOT_ID = "root";

interface ArboristTopic {
  id: string;
  name: string;
  type: "node" | "leaf";
  documentCount: number;
  conversationCount: number;
  resolutionBreakdown: ResolutionBreakdown;
  children?: ArboristTopic[];
}

function mapNode(node: TopicNode): ArboristTopic {
  return {
    id: String(node.id),
    name: node.name,
    type: node.type,
    documentCount: node.document_count,
    conversationCount: node.conversation_count,
    resolutionBreakdown: node.resolution_breakdown,
    children: node.type === "node" ? node.children.map(mapNode) : undefined,
  };
}

/** Wrap the whole tree under one always-present, always-selectable root row. */
function mapRoot(tree: TopicNode): ArboristTopic {
  return {
    id: ROOT_ID,
    name: "Todos los temas",
    type: "node",
    documentCount: tree.document_count,
    conversationCount: tree.conversation_count,
    resolutionBreakdown: tree.resolution_breakdown,
    children: tree.children.map(mapNode),
  };
}

/** react-arborist reports a "top level" drop/create as parentId=null; we file that under our root row. */
function toBackendParentId(id: string | null): number | null {
  return id === null || id === ROOT_ID ? null : Number(id);
}

function insertNode(nodes: ArboristTopic[], parentId: string | null, newNode: ArboristTopic): ArboristTopic[] {
  const targetId = parentId ?? ROOT_ID;
  return nodes.map((n) => {
    if (n.id === targetId) return { ...n, children: [...(n.children ?? []), newNode] };
    if (n.children) return { ...n, children: insertNode(n.children, parentId, newNode) };
    return n;
  });
}

function renameInTree(nodes: ArboristTopic[], id: string, name: string): ArboristTopic[] {
  return nodes.map((n) => {
    if (n.id === id) return { ...n, name };
    if (n.children) return { ...n, children: renameInTree(n.children, id, name) };
    return n;
  });
}

function removeFromTree(nodes: ArboristTopic[], id: string): { nodes: ArboristTopic[]; removed: ArboristTopic | null } {
  let removed: ArboristTopic | null = null;
  const next = nodes.filter((n) => {
    if (n.id === id) {
      removed = n;
      return false;
    }
    return true;
  });
  if (removed) return { nodes: next, removed };
  for (let i = 0; i < next.length; i++) {
    const n = next[i];
    if (n.children) {
      const result = removeFromTree(n.children, id);
      if (result.removed) {
        next[i] = { ...n, children: result.nodes };
        return { nodes: next, removed: result.removed };
      }
    }
  }
  return { nodes: next, removed: null };
}

function Node({ node, style, dragHandle, canEdit }: NodeRendererProps<ArboristTopic> & { canEdit: boolean }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const isRoot = node.data.id === ROOT_ID;

  useEffect(() => {
    if (node.isEditing) {
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [node.isEditing]);

  return (
    <div ref={dragHandle} style={style} className="tree-row" onClick={() => node.isInternal && node.toggle()}>
      <span className={`toggle${node.isOpen ? " open" : ""}`}>{node.isInternal ? "▶" : ""}</span>
      <span>{isRoot ? "🌐" : node.isLeaf ? "📄" : "📁"}</span>
      {node.isEditing ? (
        <input
          ref={inputRef}
          defaultValue={node.data.name}
          onClick={(e) => e.stopPropagation()}
          onBlur={() => node.reset()}
          onKeyDown={(e) => {
            if (e.key === "Escape") node.reset();
            if (e.key === "Enter") node.submit(inputRef.current?.value || node.data.name);
          }}
        />
      ) : (
        <span
          className={`name ${node.data.type}`}
          onDoubleClick={(e) => {
            if (canEdit && !isRoot) {
              e.stopPropagation();
              node.edit();
            }
          }}
        >
          {node.data.name}
        </span>
      )}
      {node.data.documentCount > 0 && <span className="count docs">{node.data.documentCount} doc</span>}
      {node.data.conversationCount > 0 && (
        <>
          <span className="count">{node.data.conversationCount} conv</span>
          <BreakdownBar breakdown={node.data.resolutionBreakdown} />
        </>
      )}
      {canEdit && (
        <span className="row" style={{ marginLeft: "auto", gap: 4 }}>
          {node.isInternal && (
            <button
              className="btn"
              style={{ padding: "2px 6px", fontSize: 11 }}
              onClick={(e) => {
                e.stopPropagation();
                node.open();
                node.focus();
                node.tree.createLeaf();
              }}
              title="Agregar hoja"
            >
              + hoja
            </button>
          )}
          {!isRoot && (
            <button
              className="btn danger"
              style={{ padding: "2px 6px", fontSize: 11 }}
              onClick={(e) => {
                e.stopPropagation();
                node.tree.delete(node.id);
              }}
              title="Borrar"
            >
              ✕
            </button>
          )}
        </span>
      )}
    </div>
  );
}

export function TopicArboristTree({
  tree,
  canEdit,
  onSelect,
  selectedTopicId,
  onChanged,
}: {
  tree: TopicNode;
  canEdit: boolean;
  onSelect: (topicId: number | null) => void;
  /** null = nothing selected yet; "root" = the root row is selected; number = a real topic. */
  selectedTopicId: number | "root" | null;
  onChanged: () => void;
}) {
  const [data, setData] = useState<ArboristTopic[]>(() => [mapRoot(tree)]);
  const [error, setError] = useState<string | null>(null);
  const treeRef = useRef<TreeApi<ArboristTopic> | null>(null);

  useEffect(() => setData([mapRoot(tree)]), [tree]);

  function reportError(e: unknown, fallback: string) {
    setError(e instanceof ApiError ? e.message : fallback);
  }

  const handleCreate: CreateHandler<ArboristTopic> = async ({ parentId, type }) => {
    setError(null);
    try {
      const defaultName = type === "internal" ? "Nuevo nodo" : "Nueva hoja";
      const created = await createTopic(toBackendParentId(parentId), defaultName, type === "internal" ? "node" : "leaf");
      const newNode: ArboristTopic = {
        id: String(created.id),
        name: created.name,
        type: created.type,
        documentCount: 0,
        conversationCount: 0,
        resolutionBreakdown: { resolved: 0, partial: 0, unresolved: 0, unknown: 0 },
        children: created.type === "node" ? [] : undefined,
      };
      setData((prev) => insertNode(prev, parentId, newNode));
      onChanged();
      return newNode;
    } catch (e) {
      reportError(e, "No se pudo crear el tema");
      return null;
    }
  };

  const handleRename: RenameHandler<ArboristTopic> = async ({ id, name }) => {
    if (id === ROOT_ID) return;
    setError(null);
    try {
      await renameTopic(Number(id), name);
      setData((prev) => renameInTree(prev, id, name));
      onChanged();
    } catch (e) {
      reportError(e, "No se pudo renombrar");
    }
  };

  const handleMove: MoveHandler<ArboristTopic> = async ({ dragIds, parentId }) => {
    setError(null);
    const backendParentId = toBackendParentId(parentId);
    for (const id of dragIds) {
      if (id === ROOT_ID) continue;
      try {
        await moveTopic(Number(id), backendParentId);
        setData((prev) => {
          const { nodes, removed } = removeFromTree(prev, id);
          return removed ? insertNode(nodes, parentId, removed) : prev;
        });
      } catch (e) {
        reportError(e, "No se pudo mover");
      }
    }
    onChanged();
  };

  const handleDelete: DeleteHandler<ArboristTopic> = async ({ ids }) => {
    setError(null);
    for (const id of ids) {
      if (id === ROOT_ID) continue;
      try {
        await deleteTopic(Number(id));
        setData((prev) => removeFromTree(prev, id).nodes);
      } catch (e) {
        reportError(e, "No se pudo borrar (¿tiene contenido asignado?)");
      }
    }
    onChanged();
  };

  if (tree.children.length === 0 && !canEdit) {
    return <div className="empty-state">Todavía no hay temas. Cargá documentos o corré la ingesta.</div>;
  }

  return (
    <div>
      {error && <div className="error-banner" style={{ marginBottom: 8 }}>{error}</div>}
      {canEdit && (
        <div className="row" style={{ marginBottom: 8 }}>
          <button className="btn" onClick={() => treeRef.current?.createInternal()}>
            + Nodo
          </button>
          <button className="btn" onClick={() => treeRef.current?.createLeaf()}>
            + Hoja
          </button>
        </div>
      )}
      <Tree<ArboristTopic>
        ref={treeRef}
        data={data}
        initialOpenState={{ [ROOT_ID]: true }}
        openByDefault={false}
        width="100%"
        height={420}
        indent={20}
        rowHeight={30}
        disableEdit={(d) => !canEdit || d.id === ROOT_ID}
        disableDrag={(d) => !canEdit || d.id === ROOT_ID}
        disableDrop={!canEdit}
        onCreate={handleCreate}
        onRename={handleRename}
        onMove={handleMove}
        onDelete={handleDelete}
        onActivate={(node: NodeApi<ArboristTopic>) => onSelect(node.id === ROOT_ID ? null : Number(node.id))}
        selection={
          selectedTopicId == null ? undefined : selectedTopicId === "root" ? ROOT_ID : String(selectedTopicId)
        }
      >
        {(props) => <Node {...props} canEdit={canEdit} />}
      </Tree>
    </div>
  );
}
