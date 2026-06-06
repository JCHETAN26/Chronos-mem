"""Edge-case causal-integrity tests (production-readiness checklist §3 + §4).

Covers the "Chaos Monkey" vectors:
  1. Deep nested plan graph (50 levels) — recursive CTE must not blow up.
  2. Cascading delete — deleting a root plan wipes the whole subtree, no orphans.
  3. Extreme JSONB payload (~10MB) — stored and read back intact.
  4. Pydantic input guardrail — bad argument types are rejected client-side
     (before any DB round trip).

Run with CHRONOS_DSN set.
"""

import asyncio
import json
import os
import sys
import time

import pydantic

from chronos_mem import ChronosClient, OutcomeStatus

DEPTH = int(os.getenv("EDGE_DEPTH", "50"))
PAYLOAD_MB = int(os.getenv("EDGE_PAYLOAD_MB", "10"))


async def test_deep_graph(db) -> None:
    """50-level nested plan chain; trace from root and from the leaf."""
    root = await db.create_plan(agent_id="edge", goal="depth root")
    parent_id = root.id
    leaf_id = root.id
    for d in range(1, DEPTH):
        node = await db.create_plan(
            agent_id="edge", goal=f"level {d}", parent_plan_id=parent_id
        )
        parent_id = node.id
        leaf_id = node.id

    t0 = time.perf_counter()
    trace = await db.query_causality(root.id)
    elapsed = (time.perf_counter() - t0) * 1000

    assert len(trace.subtree) == DEPTH, f"expected {DEPTH} nodes, got {len(trace.subtree)}"
    assert max(n.depth for n in trace.subtree) == DEPTH - 1
    # Trace from the leaf: ancestor path back to root must be DEPTH-1 long.
    leaf_trace = await db.query_causality(leaf_id)
    assert len(leaf_trace.ancestors) == DEPTH - 1
    print(f"[ok] {DEPTH}-deep graph traced in {elapsed:.2f}ms "
          f"(subtree={len(trace.subtree)}, leaf ancestors={len(leaf_trace.ancestors)})")


async def test_cascade_delete(db) -> None:
    """Deleting a root plan must cascade to every descendant + action/outcome/intervention."""
    root = await db.create_plan(agent_id="edge-del", goal="cascade root")
    child = await db.create_plan(agent_id="edge-del", goal="child", parent_plan_id=root.id)
    action = await db.log_action(child.id, "tool.x")
    outcome = await db.log_outcome(action.id, OutcomeStatus.FAILURE, error="boom")
    await db.log_intervention(
        outcome_id=outcome.id, agent_id="edge-del", error_type="boom",
        strategy="retry", succeeded=True,
    )

    # Hard delete the root (FK ON DELETE CASCADE should clear the whole chain).
    async with db._cursor() as cur:
        await cur.execute("DELETE FROM plans WHERE id = %s", (str(root.id),))

    # No orphans anywhere tied to this chain.
    async with db._cursor() as cur:
        await cur.execute("SELECT count(*) AS n FROM plans WHERE id = ANY(%s)",
                          ([str(root.id), str(child.id)],))
        assert (await cur.fetchone())["n"] == 0
        await cur.execute("SELECT count(*) AS n FROM actions WHERE id = %s", (str(action.id),))
        assert (await cur.fetchone())["n"] == 0
        await cur.execute("SELECT count(*) AS n FROM outcomes WHERE action_id = %s",
                          (str(action.id),))
        assert (await cur.fetchone())["n"] == 0
        await cur.execute("SELECT count(*) AS n FROM interventions WHERE outcome_id = %s",
                          (str(outcome.id),))
        assert (await cur.fetchone())["n"] == 0
    print("[ok] cascading delete left 0 orphan rows across all pillars")


async def test_extreme_payload(db) -> None:
    """~10MB nested JSONB payload stored and read back intact."""
    blob = "A" * (PAYLOAD_MB * 1024 * 1024)
    payload = {"marker": "edge", "nested": {"deep": {"blob": blob}}, "count": len(blob)}
    size_mb = len(json.dumps(payload)) / 1024 / 1024

    plan = await db.create_plan(agent_id="edge-big", goal="payload root")
    t0 = time.perf_counter()
    action = await db.log_action(plan.id, "tool.bigpayload", payload=payload)
    write_ms = (time.perf_counter() - t0) * 1000

    trace = await db.query_causality(plan.id)
    got = trace.subtree[0].actions[0].action.payload
    assert got["count"] == len(blob)
    assert got["nested"]["deep"]["blob"] == blob, "payload corrupted on round trip"
    print(f"[ok] {size_mb:.1f}MB JSONB payload round-tripped intact (write {write_ms:.0f}ms)")


async def test_input_guardrail(db) -> None:
    """Bad argument types must raise pydantic.ValidationError, not hit the DB."""
    cases = [
        ("create_plan goal=int", lambda: db.create_plan(agent_id="x", goal=123)),
        ("log_action tool=int", lambda: db.log_action(plan_id="x", tool_name=999)),
        ("log_outcome status=dict", lambda: db.log_outcome(action_id="x", status={"bad": 1})),
    ]
    for name, call in cases:
        try:
            await call()
        except pydantic.ValidationError:
            continue  # rejected client-side, as intended
        except Exception as exc:
            raise AssertionError(f"{name}: expected ValidationError, got {type(exc).__name__}") from exc
        raise AssertionError(f"{name}: bad input was NOT rejected")
    print("[ok] bad input types rejected client-side by Pydantic (no DB round trip)")


async def main() -> int:
    dsn = os.environ["CHRONOS_DSN"]
    async with ChronosClient(dsn=dsn) as db:
        await test_deep_graph(db)
        await test_cascade_delete(db)
        await test_extreme_payload(db)
        await test_input_guardrail(db)
    print("\nALL EDGE-CASE CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
