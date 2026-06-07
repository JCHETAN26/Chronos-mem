import { PLAN_TONE } from "../lib/theme";
import type { Root } from "../types";

export function Sidebar({
  roots,
  selectedId,
  onSelect,
}: {
  roots: Root[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <aside
      style={{
        width: 256,
        flexShrink: 0,
        borderRight: "1px solid var(--border)",
        background: "var(--surface)",
        display: "flex",
        flexDirection: "column",
        height: "100%",
      }}
    >
      <div style={{ padding: "18px 18px 14px", borderBottom: "1px solid var(--border)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
          <span style={{ fontSize: 18 }}>🕸️</span>
          <span style={{ fontSize: 15, fontWeight: 700, letterSpacing: -0.2 }}>
            chronos-mem
          </span>
        </div>
        <div style={{ fontSize: 11, color: "var(--text-faint)", marginTop: 3 }}>
          causal tracer
        </div>
      </div>

      <div style={{ padding: "12px 12px 6px", fontSize: 11, color: "var(--text-faint)", textTransform: "uppercase", letterSpacing: 0.5 }}>
        Recent runs
      </div>
      <div style={{ overflowY: "auto", padding: "0 8px 12px", display: "flex", flexDirection: "column", gap: 4 }}>
        {roots.map((r) => {
          const active = r.id === selectedId;
          const tone = PLAN_TONE[r.status] ?? PLAN_TONE.pending;
          return (
            <button
              key={r.id}
              onClick={() => onSelect(r.id)}
              style={{
                textAlign: "left",
                background: active ? "var(--accent-soft)" : "transparent",
                border: `1px solid ${active ? "var(--accent)" : "transparent"}`,
                borderRadius: 9,
                padding: "9px 11px",
                cursor: "pointer",
                color: "var(--text)",
                display: "flex",
                flexDirection: "column",
                gap: 3,
              }}
            >
              <span style={{ display: "flex", alignItems: "center", gap: 7 }}>
                <span style={{ width: 7, height: 7, borderRadius: 99, background: tone.color, flexShrink: 0 }} />
                <span style={{ fontSize: 13, fontWeight: 600, lineHeight: 1.25 }}>{r.goal}</span>
              </span>
              <span style={{ fontSize: 11, color: "var(--text-faint)", marginLeft: 14 }}>
                {r.agent_id}
              </span>
            </button>
          );
        })}
        {roots.length === 0 && (
          <div style={{ fontSize: 12, color: "var(--text-faint)", padding: 10 }}>
            No runs yet.
          </div>
        )}
      </div>
    </aside>
  );
}
