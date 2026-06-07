import { OUTCOME_TONE, planTone } from "../lib/theme";
import type { Action, BestIntervention, TraceNode } from "../types";

function ActionCard({
  action,
  suggestion,
}: {
  action: Action;
  suggestion: BestIntervention | null | undefined;
}) {
  const oc = action.outcome;
  const tone = oc ? OUTCOME_TONE[oc.status] : null;
  return (
    <div
      style={{
        border: "1px solid var(--border)",
        borderRadius: 10,
        padding: 12,
        background: "var(--surface)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <span className="mono" style={{ fontSize: 12.5, color: "var(--text)", fontWeight: 600 }}>
          {action.tool_name}
        </span>
        {tone && (
          <span
            style={{
              marginLeft: "auto",
              fontSize: 10.5,
              fontWeight: 600,
              color: tone.color,
              background: tone.bg,
              padding: "2px 7px",
              borderRadius: 6,
              textTransform: "uppercase",
            }}
          >
            {tone.label}
          </span>
        )}
      </div>
      {oc?.error && (
        <div
          style={{
            fontSize: 12,
            color: "var(--fail)",
            background: "var(--fail-soft)",
            border: "1px solid #ef444433",
            borderRadius: 7,
            padding: "6px 9px",
            marginBottom: 8,
          }}
          className="mono"
        >
          {oc.error}
        </div>
      )}
      {Object.keys(action.payload).length > 0 && (
        <pre
          className="mono"
          style={{
            fontSize: 11.5,
            color: "var(--text-dim)",
            background: "var(--bg)",
            border: "1px solid var(--border-soft)",
            borderRadius: 7,
            padding: "8px 10px",
            margin: 0,
            overflowX: "auto",
          }}
        >
          {JSON.stringify(action.payload, null, 2)}
        </pre>
      )}
      {action.failed && suggestion && (
        <div
          style={{
            marginTop: 8,
            fontSize: 12,
            color: "var(--ok)",
            display: "flex",
            alignItems: "center",
            gap: 6,
          }}
        >
          <span>💡 Suggested fix:</span>
          <b style={{ textTransform: "uppercase" }}>{suggestion.strategy}</b>
          <span style={{ color: "var(--text-faint)" }}>
            (worked {suggestion.success_count}×)
          </span>
        </div>
      )}
    </div>
  );
}

export function DetailDrawer({
  node,
  suggestions,
  onClose,
}: {
  node: TraceNode | null;
  suggestions: Record<string, BestIntervention | null>;
  onClose: () => void;
}) {
  if (!node) return null;
  const tone = planTone(node.status, node.failed);
  return (
    <aside
      style={{
        width: 380,
        flexShrink: 0,
        borderLeft: "1px solid var(--border)",
        background: "var(--surface)",
        display: "flex",
        flexDirection: "column",
        height: "100%",
      }}
    >
      <div
        style={{
          padding: "16px 18px",
          borderBottom: "1px solid var(--border)",
          display: "flex",
          alignItems: "flex-start",
          gap: 10,
        }}
      >
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 11, color: "var(--text-faint)", marginBottom: 4 }}>
            {node.agent_id} · depth {node.depth}
          </div>
          <div style={{ fontSize: 15, fontWeight: 700, lineHeight: 1.3 }}>{node.goal}</div>
          <span
            style={{
              display: "inline-block",
              marginTop: 8,
              fontSize: 11,
              fontWeight: 600,
              color: tone.color,
              background: tone.bg,
              padding: "2px 8px",
              borderRadius: 6,
              textTransform: "uppercase",
            }}
          >
            {tone.label}
          </span>
        </div>
        <button
          onClick={onClose}
          style={{
            background: "transparent",
            border: "none",
            color: "var(--text-faint)",
            fontSize: 18,
            cursor: "pointer",
            lineHeight: 1,
          }}
        >
          ✕
        </button>
      </div>

      <div style={{ padding: 18, overflowY: "auto", display: "flex", flexDirection: "column", gap: 10 }}>
        <div style={{ fontSize: 11, color: "var(--text-faint)", textTransform: "uppercase", letterSpacing: 0.5 }}>
          {node.actions.length} action{node.actions.length !== 1 ? "s" : ""}
        </div>
        {node.actions.length === 0 && (
          <div style={{ fontSize: 13, color: "var(--text-faint)" }}>
            No tool executions on this node.
          </div>
        )}
        {node.actions.map((a) => (
          <ActionCard
            key={a.id}
            action={a}
            suggestion={a.outcome?.error ? suggestions[a.outcome.error] : undefined}
          />
        ))}
      </div>
    </aside>
  );
}
