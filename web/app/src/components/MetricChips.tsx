import type { TraceMetrics } from "../types";

function Chip({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div
      style={{
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: 10,
        padding: "8px 14px",
        minWidth: 96,
      }}
    >
      <div style={{ fontSize: 11, color: "var(--text-faint)", letterSpacing: 0.3 }}>
        {label}
      </div>
      <div style={{ fontSize: 19, fontWeight: 700, color: tone ?? "var(--text)" }}>
        {value}
      </div>
    </div>
  );
}

export function MetricChips({ m }: { m: TraceMetrics }) {
  return (
    <div style={{ display: "flex", gap: 10 }}>
      <Chip label="Plan nodes" value={String(m.nodes)} />
      <Chip
        label="Failed nodes"
        value={String(m.failed_nodes)}
        tone={m.failed_nodes ? "var(--fail)" : undefined}
      />
      <Chip
        label="Failed actions"
        value={String(m.failed_actions)}
        tone={m.failed_actions ? "var(--fail)" : undefined}
      />
      <Chip
        label="Success rate"
        value={m.success_rate == null ? "—" : `${m.success_rate}%`}
        tone={
          m.success_rate == null
            ? undefined
            : m.success_rate >= 80
              ? "var(--ok)"
              : m.success_rate >= 50
                ? "var(--warn)"
                : "var(--fail)"
        }
      />
    </div>
  );
}
