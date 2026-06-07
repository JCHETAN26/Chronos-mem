import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { Sidebar } from "./components/Sidebar";
import { MetricChips } from "./components/MetricChips";
import { CausalGraph } from "./components/CausalGraph";
import { DetailDrawer } from "./components/DetailDrawer";
import { ToolHealth } from "./components/ToolHealth";
import type { BestIntervention, Root, ToolStat, Trace } from "./types";

type View = "graph" | "tools";

export default function App() {
  const [roots, setRoots] = useState<Root[]>([]);
  const [tools, setTools] = useState<ToolStat[]>([]);
  const [rootId, setRootId] = useState<string | null>(null);
  const [trace, setTrace] = useState<Trace | null>(null);
  const [nodeId, setNodeId] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<Record<string, BestIntervention | null>>({});
  const [view, setView] = useState<View>("graph");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .roots()
      .then((rs) => {
        setRoots(rs);
        if (rs.length) setRootId(rs[0].id);
      })
      .catch((e) => setError(String(e)));
    api.tools().then(setTools).catch(() => {});
  }, []);

  useEffect(() => {
    if (!rootId) return;
    setNodeId(null);
    api
      .trace(rootId)
      .then(async (t) => {
        setTrace(t);
        const errs = Array.from(
          new Set(
            t.nodes.flatMap((n) =>
              n.actions.filter((a) => a.failed && a.outcome?.error).map((a) => a.outcome!.error as string),
            ),
          ),
        );
        const entries = await Promise.all(
          errs.map(async (e) => [e, await api.bestIntervention(e)] as const),
        );
        setSuggestions(Object.fromEntries(entries));
      })
      .catch((e) => setError(String(e)));
  }, [rootId]);

  const selectedNode = useMemo(
    () => trace?.nodes.find((n) => n.id === nodeId) ?? null,
    [trace, nodeId],
  );

  if (error) {
    return (
      <div style={{ height: "100%", display: "grid", placeItems: "center", padding: 24 }}>
        <div style={{ maxWidth: 460, textAlign: "center" }}>
          <div style={{ fontSize: 32, marginBottom: 8 }}>🔌</div>
          <h2 style={{ margin: "0 0 8px" }}>Can't reach the API</h2>
          <p style={{ color: "var(--text-dim)", fontSize: 13 }}>
            Start it with{" "}
            <span className="mono" style={{ color: "var(--text)" }}>
              uvicorn main:app --port 8000
            </span>{" "}
            from <span className="mono">web/api/</span>.
          </p>
          <pre className="mono" style={{ color: "var(--fail)", fontSize: 12 }}>{error}</pre>
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", height: "100%", overflow: "hidden" }}>
      <Sidebar roots={roots} selectedId={rootId} onSelect={setRootId} />

      <main style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        {/* top bar */}
        <div
          style={{
            padding: "14px 22px",
            borderBottom: "1px solid var(--border)",
            display: "flex",
            alignItems: "center",
            gap: 18,
            background: "var(--bg)",
          }}
        >
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 11, color: "var(--text-faint)" }}>
              {trace?.ancestors.length
                ? trace.ancestors.map((a) => a.goal).join("  ›  ") + "  ›"
                : "Run"}
            </div>
            <div
              style={{
                fontSize: 17,
                fontWeight: 700,
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
            >
              {roots.find((r) => r.id === rootId)?.goal ?? "Select a run"}
            </div>
          </div>

          <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 16 }}>
            {trace && <MetricChips m={trace.metrics} />}
            <Segmented value={view} onChange={setView} />
          </div>
        </div>

        {/* content */}
        <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
          {view === "graph" ? (
            <>
              <div style={{ flex: 1, minWidth: 0 }}>
                {trace && (
                  <CausalGraph trace={trace} selectedId={nodeId} onSelect={setNodeId} />
                )}
              </div>
              <DetailDrawer
                node={selectedNode}
                suggestions={suggestions}
                onClose={() => setNodeId(null)}
              />
            </>
          ) : (
            <ToolHealth tools={tools} />
          )}
        </div>
      </main>
    </div>
  );
}

function Segmented({ value, onChange }: { value: View; onChange: (v: View) => void }) {
  const opts: { id: View; label: string }[] = [
    { id: "graph", label: "🗺  Graph" },
    { id: "tools", label: "🧰  Tools" },
  ];
  return (
    <div
      style={{
        display: "flex",
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: 9,
        padding: 3,
      }}
    >
      {opts.map((o) => (
        <button
          key={o.id}
          onClick={() => onChange(o.id)}
          style={{
            border: "none",
            cursor: "pointer",
            fontSize: 12.5,
            fontWeight: 600,
            padding: "6px 13px",
            borderRadius: 6,
            color: value === o.id ? "var(--text)" : "var(--text-faint)",
            background: value === o.id ? "var(--surface-2)" : "transparent",
          }}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
