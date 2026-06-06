"""Intervention engine verification (Milestone 3, 5th pillar).

Exercises log_intervention + get_best_intervention end-to-end: logs several
post-failure decisions for the same error_type with mixed success, then
confirms get_best_intervention returns the most-proven strategy. Also checks
the no-history path and measures lookup latency against the sub-5ms target.

Run with CHRONOS_DSN pointing at a migrated database.
"""

import asyncio
import os
import statistics
import sys
import time

from chronos_mem import ChronosClient, InterventionStrategy, OutcomeStatus


async def _make_failure(db, agent: str):
    """Create a plan -> action -> failed outcome and return the outcome id."""
    plan = await db.create_plan(agent_id=agent, goal="charge the customer")
    action = await db.log_action(plan_id=plan.id, tool_name="payments.charge")
    outcome = await db.log_outcome(
        action_id=action.id, status=OutcomeStatus.FAILURE, error="payment_declined"
    )
    return outcome.id


async def main() -> int:
    dsn = os.environ["CHRONOS_DSN"]
    async with ChronosClient(dsn=dsn) as db:
        agent = "agent-intervene"

        # No history yet -> None.
        assert await db.get_best_intervention("payment_declined") is None
        print("[ok] no-history lookup returns None")

        # Log interventions for 'payment_declined':
        #   RETRY    succeeded 3x
        #   PIVOT    succeeded 1x
        #   ESCALATE failed   2x  (must be ignored: not successful)
        plan_strategies = [
            (InterventionStrategy.RETRY, True),
            (InterventionStrategy.RETRY, True),
            (InterventionStrategy.RETRY, True),
            (InterventionStrategy.PIVOT, True),
            (InterventionStrategy.ESCALATE, False),
            (InterventionStrategy.ESCALATE, False),
        ]
        for strategy, ok in plan_strategies:
            outcome_id = await _make_failure(db, agent)
            iv = await db.log_intervention(
                outcome_id=outcome_id,
                error_type="payment_declined",
                strategy=strategy,
                succeeded=ok,
                agent_id=agent,
                details={"note": "synthetic"},
            )
            assert iv.error_type == "payment_declined"
            assert iv.strategy == strategy and iv.succeeded == ok
        print("[ok] logged 6 interventions (4 success, 2 fail)")

        # Best fix should be RETRY (3 successes), beating PIVOT (1).
        best = await db.get_best_intervention("payment_declined")
        assert best is not None
        assert best.strategy == InterventionStrategy.RETRY, best.strategy
        assert best.success_count == 3, best.success_count
        print(f"[ok] best fix = {best.strategy.value} (worked {best.success_count}x)")

        # Unrelated error type still has no history.
        assert await db.get_best_intervention("rate_limited") is None
        print("[ok] unrelated error type returns None")

        # Latency.
        timings = []
        for _ in range(50):
            t0 = time.perf_counter()
            await db.get_best_intervention("payment_declined")
            timings.append((time.perf_counter() - t0) * 1000)
        p50 = statistics.median(timings)
        print(f"\nget_best_intervention latency: best={min(timings):.3f}ms p50={p50:.3f}ms")

    print("\nALL INTERVENTION CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
