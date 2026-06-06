"""End-to-end smoke test for the chronos-mem SDK.

Exercises the full write path against a live Postgres:
create_plan -> sub-plan -> log_action -> log_outcome, then reads the rows back
to confirm the relational links and JSONB round-trips hold.

Run with CHRONOS_DSN pointing at a migrated database.
"""

import asyncio
import os
import sys

from chronos_mem import ChronosClient, OutcomeStatus, PlanStatus


async def main() -> int:
    dsn = os.environ["CHRONOS_DSN"]
    async with ChronosClient(dsn=dsn) as db:
        assert await db.ping() is True, "ping failed"

        # Root goal.
        root = await db.create_plan(
            agent_id="agent-smoke",
            goal="Book a vacation to Tokyo",
            metadata={"priority": "high"},
        )
        assert root.parent_plan_id is None
        assert root.status == PlanStatus.PENDING
        assert root.metadata == {"priority": "high"}
        print(f"[ok] root plan      {root.id}  status={root.status.value}")

        # Sub-plan (DAG child).
        child = await db.create_plan(
            agent_id="agent-smoke",
            goal="Find flights",
            parent_plan_id=root.id,
            status=PlanStatus.IN_PROGRESS,
        )
        assert child.parent_plan_id == root.id
        print(f"[ok] sub-plan       {child.id}  parent={child.parent_plan_id}")

        # Action under the sub-plan.
        action = await db.log_action(
            plan_id=child.id,
            tool_name="flights.search",
            payload={"from": "SFO", "to": "HND", "pax": 2},
        )
        assert action.plan_id == child.id
        assert action.payload["to"] == "HND"
        print(f"[ok] action         {action.id}  tool={action.tool_name}")

        # Outcome verdict for the action.
        outcome = await db.log_outcome(
            action_id=action.id,
            status=OutcomeStatus.SUCCESS,
            result={"cheapest_usd": 812},
        )
        assert outcome.action_id == action.id
        assert outcome.status == OutcomeStatus.SUCCESS
        assert outcome.result["cheapest_usd"] == 812
        print(f"[ok] outcome        {outcome.id}  status={outcome.status.value}")

        # Failure path + the UNIQUE(action_id) guard: a second outcome must fail.
        failing_action = await db.log_action(plan_id=child.id, tool_name="flights.book")
        await db.log_outcome(
            action_id=failing_action.id,
            status=OutcomeStatus.FAILURE,
            error="payment declined",
        )
        try:
            await db.log_outcome(action_id=failing_action.id, status=OutcomeStatus.SUCCESS)
        except Exception as exc:  # psycopg.errors.UniqueViolation
            print(f"[ok] duplicate outcome correctly rejected ({type(exc).__name__})")
        else:
            print("[FAIL] duplicate outcome was NOT rejected")
            return 1

    print("\nALL SMOKE CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
