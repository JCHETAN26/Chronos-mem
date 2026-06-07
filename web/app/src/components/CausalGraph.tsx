import { useMemo } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { PlanNode } from "./PlanNode";
import { layout } from "../lib/layout";
import type { Trace } from "../types";

const nodeTypes = { plan: PlanNode };

export function CausalGraph({
  trace,
  selectedId,
  onSelect,
}: {
  trace: Trace;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const { nodes, edges } = useMemo(() => {
    const ids = new Set(trace.nodes.map((n) => n.id));
    const rfNodes: Node[] = trace.nodes.map((n) => ({
      id: n.id,
      type: "plan",
      position: { x: 0, y: 0 },
      data: {
        goal: n.goal,
        status: n.status,
        failed: n.failed,
        actionCount: n.actions.length,
        failedActions: n.actions.filter((a) => a.failed).length,
        isRoot: n.id === trace.plan_id,
        selected: n.id === selectedId,
      },
    }));
    const rfEdges: Edge[] = trace.nodes
      .filter((n) => n.parent_id && ids.has(n.parent_id))
      .map((n) => ({
        id: `${n.parent_id}->${n.id}`,
        source: n.parent_id as string,
        target: n.id,
        animated: n.failed,
        style: {
          stroke: n.failed ? "#ef4444" : "#2a3340",
          strokeWidth: n.failed ? 2 : 1.5,
        },
      }));
    return { nodes: layout(rfNodes, rfEdges), edges: rfEdges };
  }, [trace, selectedId]);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      onNodeClick={(_, node) => onSelect(node.id)}
      fitView
      fitViewOptions={{ padding: 0.2 }}
      minZoom={0.2}
      maxZoom={1.6}
      proOptions={{ hideAttribution: true }}
    >
      <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="#1c2430" />
      <Controls showInteractive={false} />
    </ReactFlow>
  );
}
