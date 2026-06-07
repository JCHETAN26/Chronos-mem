export type PlanStatus =
  | "pending"
  | "in_progress"
  | "completed"
  | "failed"
  | "abandoned";

export type OutcomeStatus = "success" | "failure" | "partial" | "error";

export interface Root {
  id: string;
  agent_id: string;
  goal: string;
  status: PlanStatus;
  created_at: string;
}

export interface Outcome {
  status: OutcomeStatus;
  result: Record<string, unknown>;
  error: string | null;
  created_at: string;
}

export interface Action {
  id: string;
  tool_name: string;
  payload: Record<string, unknown>;
  created_at: string;
  failed: boolean;
  outcome: Outcome | null;
}

export interface TraceNode {
  id: string;
  parent_id: string | null;
  agent_id: string;
  goal: string;
  status: PlanStatus;
  depth: number;
  failed: boolean;
  actions: Action[];
}

export interface TraceMetrics {
  nodes: number;
  failed_nodes: number;
  total_actions: number;
  failed_actions: number;
  success_rate: number | null;
}

export interface Ancestor {
  id: string;
  agent_id: string;
  goal: string;
  status: PlanStatus;
}

export interface Trace {
  plan_id: string;
  ancestors: Ancestor[];
  nodes: TraceNode[];
  metrics: TraceMetrics;
}

export interface BestIntervention {
  error_type: string;
  strategy: string;
  success_count: number;
  last_used: string;
}

export interface ToolStat {
  tool_name: string;
  total_calls: number;
  successes: number;
  failures: number;
  partials: number;
  failure_rate: number;
  last_seen: string;
}
