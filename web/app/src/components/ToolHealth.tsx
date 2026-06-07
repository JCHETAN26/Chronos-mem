import type { ToolStat } from "../types";

function rateColor(rate: number): string {
  if (rate >= 0.5) return "#ef4444";
  if (rate > 0) return "#f59e0b";
  return "#22c55e";
}

export function ToolHealth({ tools }: { tools: ToolStat[] }) {
  if (tools.length === 0) {
    return (
      <div style={{ color: "var(--text-faint)", padding: 24 }}>
        No tool executions recorded yet.
      </div>
    );
  }
  const sorted = [...tools].sort((a, b) => b.failure_rate - a.failure_rate);
  return (
    <div style={{ padding: "20px 24px", overflowY: "auto", height: "100%" }}>
      <h2 style={{ fontSize: 15, fontWeight: 700, margin: "0 0 4px" }}>Tool health</h2>
      <p style={{ fontSize: 13, color: "var(--text-dim)", margin: "0 0 18px" }}>
        Failure rate by tool across all agents — surfaced from the{" "}
        <span className="mono">tool_brittleness</span> view.
      </p>
      <div style={{ display: "flex", flexDirection: "column", gap: 12, maxWidth: 760 }}>
        {sorted.map((t) => (
          <div
            key={t.tool_name}
            style={{
              display: "grid",
              gridTemplateColumns: "190px 1fr 120px",
              alignItems: "center",
              gap: 14,
            }}
          >
            <span className="mono" style={{ fontSize: 12.5, color: "var(--text)" }}>
              {t.tool_name}
            </span>
            <div
              style={{
                height: 10,
                background: "var(--surface-2)",
                border: "1px solid var(--border)",
                borderRadius: 6,
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  width: `${Math.max(t.failure_rate * 100, t.failures ? 3 : 0)}%`,
                  height: "100%",
                  background: rateColor(t.failure_rate),
                  transition: "width .3s",
                }}
              />
            </div>
            <span style={{ fontSize: 12, color: "var(--text-dim)", textAlign: "right" }}>
              <b style={{ color: rateColor(t.failure_rate) }}>
                {Math.round(t.failure_rate * 100)}%
              </b>{" "}
              · {t.failures}/{t.total_calls}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
