import type { OutcomeStatus, PlanStatus } from "../types";

export interface StatusTone {
  /** dot / accent colour */
  color: string;
  /** translucent chip background */
  bg: string;
  label: string;
}

export const PLAN_TONE: Record<PlanStatus, StatusTone> = {
  pending: { color: "#8b95a7", bg: "#8b95a722", label: "Pending" },
  in_progress: { color: "#60a5fa", bg: "#60a5fa22", label: "In progress" },
  completed: { color: "#22c55e", bg: "#22c55e22", label: "Completed" },
  failed: { color: "#ef4444", bg: "#ef444422", label: "Failed" },
  abandoned: { color: "#a78bfa", bg: "#a78bfa22", label: "Abandoned" },
};

export const OUTCOME_TONE: Record<OutcomeStatus, StatusTone> = {
  success: { color: "#22c55e", bg: "#22c55e22", label: "success" },
  failure: { color: "#ef4444", bg: "#ef444422", label: "failure" },
  partial: { color: "#f59e0b", bg: "#f59e0b22", label: "partial" },
  error: { color: "#ef4444", bg: "#ef444422", label: "error" },
};

export function planTone(status: PlanStatus, failed: boolean): StatusTone {
  return failed ? PLAN_TONE.failed : PLAN_TONE[status] ?? PLAN_TONE.pending;
}
