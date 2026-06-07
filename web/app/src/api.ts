import type { BestIntervention, Root, ToolStat, Trace } from "./types";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path} → HTTP ${res.status}`);
  return res.json() as Promise<T>;
}

export const api = {
  roots: () => get<Root[]>("/api/roots"),
  trace: (planId: string) => get<Trace>(`/api/trace/${planId}`),
  tools: () => get<ToolStat[]>("/api/tools"),
  bestIntervention: (errorType: string) =>
    get<BestIntervention | null>(
      `/api/best-intervention?error_type=${encodeURIComponent(errorType)}`,
    ),
};
