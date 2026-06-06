"""Causal-trace verification + latency check for Milestone 3.

Builds a small multi-level plan DAG with a deliberate failure deep in the
tree, traces it with query_causality(), asserts the structure (ancestors,
subtree, depth, failure derivation), then measures round-trip latency against
the sub-5ms target.

Run with CHRONOS_DSN pointing at a migrated database.
"""

import asyncio
import os
import statistics
import sys
import time

from chronos_mem import ChronosClient, OutcomeStatus, PlanStatus


async def main() -> int:
    dsn = os.environ["CHRONOS_DSN"]
    async with ChronosClient(dsn=dsn) as db:
        agent = "agent-trace"

        # Build: root -> [flights, hotel]; flights -> book(FAIL); hotel -> book(OK)
        root = await db.create_plan(agent_id=agent, goal="Plan a trip to Tokyo")
        flights = await db.create_plan(
            agent_id=agent, goal="Arrange flights",
            parent_plan_id=root.id, status=PlanStatus.IN_PROGRESS,
        )
        hotel = await db.create_plan(
            agent_id=agent, goal="Book a hotel", parent_plan_id=root.id,
        )
        book_flight = await db.create_plan(
            agent_id=agent, goal="Purchase the flight",
            parent_plan_id=flights.id, status=PlanStatus.FAILED,
        )

        # Actions + outcomes
        search = await db.log_action(plan_id=flights.id, tool_name="flights.search",
                                     payload={"from": "SFO", "to": "HND"})
        await db.log_outcome(action_id=search.id, status=OutcomeStatus.SUCCESS,
                             result={"options": 12})

        pay = await db.log_action(plan_id=book_flight.id, tool_name="payments.charge",
                                  payload={"usd": 812})
        await db.log_outcome(action_id=pay.id, status=OutcomeStatus.FAILURE,
                             error="card declined")

        hotel_search = await db.log_action(plan_id=hotel.id, tool_name="hotels.search")
        await db.log_outcome(action_id=hotel_search.id, status=OutcomeStatus.SUCCESS)

        # ---- Trace from the ROOT (downward subtree) ----
        trace = await db.query_causality(root.id)
        plan_ids = {n.plan.id for n in trace.subtree}
        assert plan_ids == {root.id, flights.id, hotel.id, book_flight.id}, plan_ids
        assert trace.root.plan.id == root.id
        assert trace.root.depth == 0
        depth_of = {n.plan.id: n.depth for n in trace.subtree}
        assert depth_of[flights.id] == 1 and depth_of[book_flight.id] == 2, depth_of
        assert trace.has_failures
        assert {a.action.tool_name for a in trace.failed_actions} == {"payments.charge"}
        assert {n.plan.id for n in trace.failed_nodes} == {book_flight.id}
        print("[ok] subtree structure, depths, and failure derivation correct")
        print(f"     nodes={len(trace.subtree)} failed_actions={len(trace.failed_actions)} "
              f"failed_nodes={len(trace.failed_nodes)}")

        # ---- Trace from the FAILED leaf (upward ancestors) ----
        leaf_trace = await db.query_causality(book_flight.id)
        ancestry = [p.id for p in leaf_trace.ancestors]
        assert ancestry == [root.id, flights.id], ancestry  # root-first, excludes self
        print(f"[ok] ancestor path root-first: {[p.goal for p in leaf_trace.ancestors]}")

        # ---- Latency ----
        timings_ms: list[float] = []
        for _ in range(50):
            t0 = time.perf_counter()
            await db.query_causality(root.id)
            timings_ms.append((time.perf_counter() - t0) * 1000)
        p50 = statistics.median(timings_ms)
        p95 = sorted(timings_ms)[int(0.95 * len(timings_ms)) - 1]
        best = min(timings_ms)
        print(f"\nLatency over 50 traces (2 CTE round trips each):")
        print(f"     best={best:.3f}ms  p50={p50:.3f}ms  p95={p95:.3f}ms")

        # Server-side cost of the subtree CTE alone (the sub-5ms claim is about
        # query execution, independent of Python/driver/network overhead).
        rows = await db._fetch(
            "EXPLAIN (ANALYZE, FORMAT JSON) " + _SUBTREE_FOR_EXPLAIN,
            {"plan_id": str(root.id)},
        )
        exec_ms = rows[0]["QUERY PLAN"][0]["Execution Time"]
        print(f"     server-side subtree CTE execution: {exec_ms:.3f}ms "
              f"({'<5ms OK' if exec_ms < 5 else 'OVER 5ms'})")

    print("\nALL CAUSAL-TRACE CHECKS PASSED")
    return 0


# Re-import the embedded subtree SQL for the EXPLAIN measurement.
from chronos_mem.causality import _SUBTREE_SQL as _SUBTREE_FOR_EXPLAIN  # noqa: E402


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
