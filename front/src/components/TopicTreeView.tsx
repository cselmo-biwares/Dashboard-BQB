import { useState } from "react";
import type { TopicNode } from "../types";
import { BreakdownBar } from "./BreakdownBar";

function TreeNodeRow({
  node,
  depth,
  onSelectNode,
  selectedTopicId,
}: {
  node: TopicNode;
  depth: number;
  onSelectNode: (node: TopicNode) => void;
  selectedTopicId: number | null;
}) {
  const [open, setOpen] = useState(depth === 0);
  const hasChildren = node.type === "node" && node.children.length > 0;
  const isLeaf = node.type === "leaf";

  return (
    <li>
      <div
        className="tree-row"
        style={
          selectedTopicId === node.id
            ? { background: "color-mix(in srgb, var(--series-1) 10%, transparent)" }
            : undefined
        }
        onClick={() => {
          if (hasChildren) setOpen((o) => !o);
          // Selecting a node shows aggregated stats over its whole subtree, not just leaves.
          onSelectNode(node);
        }}
      >
        <span className={`toggle${open ? " open" : ""}`}>{hasChildren ? "▶" : ""}</span>
        <span>{isLeaf ? "📄" : "📁"}</span>
        <span className={`name ${node.type}`}>{node.name}</span>
        {node.document_count > 0 && <span className="count docs">{node.document_count} doc</span>}
        {node.conversation_count > 0 && (
          <>
            <span className="count">{node.conversation_count} conv</span>
            <BreakdownBar breakdown={node.resolution_breakdown} />
          </>
        )}
      </div>
      {hasChildren && open && (
        <ul>
          {node.children.map((child) => (
            <TreeNodeRow
              key={`${child.type}-${child.id ?? child.name}`}
              node={child}
              depth={depth + 1}
              onSelectNode={onSelectNode}
              selectedTopicId={selectedTopicId}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

export function TopicTreeView({
  root,
  onSelectNode,
  selectedTopicId,
}: {
  root: TopicNode;
  onSelectNode: (node: TopicNode) => void;
  selectedTopicId: number | null;
}) {
  if (root.children.length === 0) {
    return <div className="empty-state">Todavía no hay temas. Cargá documentos o corré la ingesta.</div>;
  }
  return (
    <div className="tree">
      <ul>
        {root.children.map((child) => (
          <TreeNodeRow
            key={`${child.type}-${child.id ?? child.name}`}
            node={child}
            depth={0}
            onSelectNode={onSelectNode}
            selectedTopicId={selectedTopicId}
          />
        ))}
      </ul>
    </div>
  );
}
