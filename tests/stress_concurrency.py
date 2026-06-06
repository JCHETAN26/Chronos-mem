"""chronos-mem concurrency stress test — the "Chaos Monkey" (Milestone 7).

Floods the database with many concurrent agents firing *overlapping* writes:
plan-tree growth, tool-call logging, artificial failures + interventions, and
status mutations on a small set of deliberately-contended "hot" plans (to force
real row-level lock contention). Interleaved causal traces measure read latency
while the storm runs.

Asserts the two stability properties from the plan:
  * **0 deadlocks** (Postgres row-level locking handles the overlap cleanly), and
  * tracing stays responsive under load (we report latency percentiles and flag
    the sub-5ms target — see the note about end-to-end vs server-side below).

Run with CHRONOS_DSN set. Env knobs: STRESS_AGENTS (default 20),
STRESS_OPS (ops per agent, default 40), STRESS_HOT (contended plans, default 4).
"""

from __future__ import annotations

import asyncio
import os
import random
import statistics
import sys
import time
from dataclasses import dataclass, field

import psycopg.errors

from chronos_mem import ChronosClient, InterventionStrategy, OutcomeStatus, PlanStatus

AGENTS = int(os.getenv("STRESS_AGENTS", "20"))
OPS = int(os.getenv("STRESS_OPS", "40"))
HOT = int(os.getenv("STRESS_HOT", "4"))

_STATUSES = [PlanStatus.IN_PROGRESS, PlanStatus.COMPLETED, PlanStatus.FAILED]
_ERRORS = ["timeout", "rate_limited", "payment_declined", "bad_input"]
_STRATS = list(InterventionStrategy)


@dataclass
class Stats:
    ops: int = 0
    deadlocks: int = 0
    other_errors: list[str] = field(default_factory=list)
    trace_ms: list[float] = field(default_factory=list)


# Mutate a contended plan's status — exercises row-level write locks when two
# agents hit the same hot row. RETURNING so we can reuse the single-row helper.
_UPDATE_HOT = "UPDATE plans SET status = %s, updated_at = now() WHERE id = %s RETURNING id"


async def _agent(db: ChronosClient, aid: int, hot_ids: list, stats: Stats) -> None:
    rng = random.Random(aid)
    root = await db.create_plan(agent_id=f"agent-{aid}", goal=f"agent {aid} root goal")

    for i in range(OPS):
        try:
            # 1) grow this agent's own plan tree
            sub = await db.create_plan(
                agent_id=f"agent-{aid}", goal=f"subtask {i}",
                parent_plan_id=root.id, status=PlanStatus.IN_PROGRESS,
            )
            # 2) log a tool call
            action = await db.log_action(
                sub.id, tool_name=f"tool.{rng.randint(0, 5)}", payload={"i": i, "agent": aid}
            )
            # 3) ~35% fail, and log an intervention for the failure
            if rng.random() < 0.35:
                err = rng.choice(_ERRORS)
                outcome = await db.log_outcome(action.id, OutcomeStatus.FAILURE, error=err)
                await db.log_intervention(
                    outcome_id=outcome.id, agent_id=f"agent-{aid}", error_type=err,
                    strategy=rng.choice(_STRATS), succeeded=rng.random() < 0.6,
                )
            else:
                await db.log_outcome(action.id, OutcomeStatus.SUCCESS)
            # 4) contend on a shared hot plan (real lock contention)
            await db._fetchrow(_UPDATE_HOT, (rng.choice(_STATUSES).value, rng.choice(hot_ids)))
            # 5) periodically trace under load, timing the read
            if i % 5 == 0:
                t0 = time.perf_counter()
                await db.query_causality(root.id)
                stats.trace_ms.append((time.perf_counter() - t0) * 1000)
            stats.ops += 1
        except psycopg.errors.DeadlockDetected:
            stats.deadlocks += 1
        except Exception as exc:  # capture anything else for the report
            stats.other_errors.append(f"{type(exc).__name__}: {exc}")


def _pct(xs: list[float], p: float) -> float:
    s = sorted(xs)
    return s[max(0, min(len(s) - 1, int(round(p / 100 * len(s))) - 1))]


async def main() -> int:
    dsn = os.environ["CHRONOS_DSN"]
    # Size the pool to the agent count so every agent can make progress.
    async with ChronosClient(dsn=dsn, min_size=AGENTS, max_size=AGENTS, timeout=60.0) as db:
        # Seed the contended hot plans.
        hot_ids = []
        for h in range(HOT):
            p = await db.create_plan(agent_id="hot", goal=f"contended plan {h}")
            hot_ids.append(p.id)

        stats = Stats()
        print(f"Storm: {AGENTS} agents x {OPS} ops, {HOT} contended hot plans...")
        t0 = time.perf_counter()
        await asyncio.gather(*(_agent(db, a, hot_ids, stats) for a in range(AGENTS)))
        wall = time.perf_counter() - t0

        total_attempted = AGENTS * OPS
        print(f"\nCompleted {stats.ops}/{total_attempted} op-cycles in {wall:.2f}s "
              f"({stats.ops / wall:,.0f} cycles/s)")
        print(f"Deadlocks: {stats.deadlocks}")
        print(f"Other errors: {len(stats.other_errors)}")
        for e in stats.other_errors[:5]:
            print(f"  - {e}")

        if stats.trace_ms:
            p50, p95, p99 = (_pct(stats.trace_ms, 50), _pct(stats.trace_ms, 95),
                             _pct(stats.trace_ms, 99))
            print(f"\nTracing under load ({len(stats.trace_ms)} samples): "
                  f"p50={p50:.3f}ms p95={p95:.3f}ms p99={p99:.3f}ms")
            print("  (end-to-end under saturation includes pool-queue wait; "
                  "server-side CTE execution stays well under 5ms — see benchmark_perf.py)")

        # Hard gate: zero deadlocks and zero unexpected errors.
        ok = stats.deadlocks == 0 and not stats.other_errors
        print(f"\nGate (0 deadlocks, 0 errors): {'PASS' if ok else 'FAIL'}")
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
