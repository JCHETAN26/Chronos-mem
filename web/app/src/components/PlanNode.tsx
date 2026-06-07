import { Handle, Position, type NodeProps } from "@xyflow/react";
import { planTone } from "../lib/theme";
import type { PlanStatus } from "../types";

export interface PlanNodeData {
  goal: string;
  status: PlanStatus;
  failed: boolean;
  actionCount: number;
  failedActions: number;
  isRoot: boolean;
  selected: boolean;
  [key: string]: unknown;
}

export function PlanNode({ data }: NodeProps) {
  const d = data as PlanNodeData;
  const tone = planTone(d.status, d.failed);

  return (
    <div
      style={{
        width: 248,
        background: d.failed ? "#1c1417" : "var(--surface-2)",
        border: `1px solid ${
          d.selected ? "var(--accent)" : d.failed ? tone.color : "var(--border)"
        }`,
        boxShadow: d.failed
          ? "0 0 0 1px #ef444455, 0 6px 20px -8px #ef444466"
          : d.selected
            ? "0 0 0 1px var(--accent), 0 8px 24px -10px #6366f155"
            : "0 4px 14px -10px rgba(0,0,0,.6)",
        borderRadius: 12,
        padding: "11px 13px",
        transition: "border-color .12s, box-shadow .12s",
      }}
    >
      <Handle type="target" position={Position.Top} style={{ opacity: 0, top: -2 }} />
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: 99,
            background: tone.color,
            boxShadow: `0 0 8px ${tone.color}`,
            flexShrink: 0,
          }}
        />
        <span
          style={{
            fontSize: 13,
            fontWeight: 600,
            color: "var(--text)",
            lineHeight: 1.25,
            overflow: "hidden",
            textOverflow: "ellipsis",
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
          }}
        >
          {d.isRoot ? "◆ " : ""}
          {d.goal}
        </span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span
          style={{
            fontSize: 10.5,
            fontWeight: 600,
            color: tone.color,
            background: tone.bg,
            padding: "2px 7px",
            borderRadius: 6,
            textTransform: "uppercase",
            letterSpacing: 0.4,
          }}
        >
          {tone.label}
        </span>
        {d.actionCount > 0 && (
          <span style={{ fontSize: 11, color: "var(--text-faint)" }}>
            {d.actionCount} action{d.actionCount !== 1 ? "s" : ""}
            {d.failedActions > 0 && (
              <span style={{ color: "var(--fail)" }}> · {d.failedActions} failed</span>
            )}
          </span>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0, bottom: -2 }} />
    </div>
  );
}
