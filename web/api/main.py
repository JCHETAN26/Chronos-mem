"""chronos-mem web API — a thin JSON layer over the SDK for the React dashboard.

Exposes recent root goals, full causal traces, best-intervention lookups, and
tool-brittleness stats as plain JSON (UUIDs/timestamps stringified) so the
frontend can render an interactive view.

Run:
    pip install -r web/api/requirements.txt
    CHRONOS_DSN="postgresql://chronos:chronos@localhost:5432/chronos_mem" \
        uvicorn main:app --reload --port 8000      # from web/api/
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from chronos_mem import CausalTrace, ChronosClient

_RECENT_ROOTS_SQL = """
SELECT id, agent_id, goal, status, created_at
FROM plans
WHERE parent_plan_id IS NULL
ORDER BY created_at DESC
LIMIT 100;
"""

_db: ChronosClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _db
    dsn = os.getenv("CHRONOS_DSN", "postgresql://chronos:chronos@localhost:5432/chronos_mem")
    _db = ChronosClient(dsn=dsn, min_size=1, max_size=8)
    await _db.open()
    try:
        yield
    finally:
        await _db.close()


app = FastAPI(title="chronos-mem API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def db() -> ChronosClient:
    if _db is None:
        raise HTTPException(503, "database not ready")
    return _db


# --- serialization ---------------------------------------------------------

def _trace_to_json(trace: CausalTrace) -> dict[str, Any]:
    total_actions = sum(len(n.actions) for n in trace.subtree)
    failed_actions = len(trace.failed_actions)
    return {
        "plan_id": str(trace.plan_id),
        "ancestors": [
            {"id": str(p.id), "agent_id": p.agent_id, "goal": p.goal,
             "status": p.status.value}
            for p in trace.ancestors
        ],
        "nodes": [
            {
                "id": str(n.plan.id),
                "parent_id": str(n.plan.parent_plan_id) if n.plan.parent_plan_id else None,
                "agent_id": n.plan.agent_id,
                "goal": n.plan.goal,
                "status": n.plan.status.value,
                "depth": n.depth,
                "failed": n.failed,
                "actions": [
                    {
                        "id": str(a.action.id),
                        "tool_name": a.action.tool_name,
                        "payload": a.action.payload,
                        "created_at": a.action.created_at.isoformat(),
                        "failed": a.failed,
                        "outcome": (
                            {
                                "status": a.outcome.status.value,
                                "result": a.outcome.result,
                                "error": a.outcome.error,
                                "created_at": a.outcome.created_at.isoformat(),
                            }
                            if a.outcome else None
                        ),
                    }
                    for a in n.actions
                ],
            }
            for n in trace.subtree
        ],
        "metrics": {
            "nodes": len(trace.subtree),
            "failed_nodes": len(trace.failed_nodes),
            "total_actions": total_actions,
            "failed_actions": failed_actions,
            "success_rate": (
                round(100 * (total_actions - failed_actions) / total_actions)
                if total_actions else None
            ),
        },
    }


# --- routes ----------------------------------------------------------------

@app.get("/api/health")
async def health() -> dict[str, bool]:
    return {"ok": await db().ping()}


@app.get("/api/roots")
async def roots() -> list[dict[str, Any]]:
    rows = await db()._fetch(_RECENT_ROOTS_SQL, {})
    return [
        {"id": str(r["id"]), "agent_id": r["agent_id"], "goal": r["goal"],
         "status": r["status"], "created_at": r["created_at"].isoformat()}
        for r in rows
    ]


@app.get("/api/trace/{plan_id}")
async def trace(plan_id: str) -> dict[str, Any]:
    try:
        t = await db().query_causality(plan_id)
    except LookupError:
        raise HTTPException(404, f"no plan {plan_id}")
    return _trace_to_json(t)


@app.get("/api/best-intervention")
async def best_intervention(error_type: str) -> dict[str, Any] | None:
    best = await db().get_best_intervention(error_type)
    if best is None:
        return None
    return {
        "error_type": best.error_type,
        "strategy": best.strategy.value,
        "success_count": best.success_count,
        "last_used": best.last_used.isoformat(),
    }


@app.get("/api/tools")
async def tools() -> list[dict[str, Any]]:
    rows = await db().tool_brittleness()
    return [
        {
            "tool_name": b.tool_name, "total_calls": b.total_calls,
            "successes": b.successes, "failures": b.failures,
            "partials": b.partials, "failure_rate": b.failure_rate,
            "last_seen": b.last_seen.isoformat(),
        }
        for b in rows
    ]
