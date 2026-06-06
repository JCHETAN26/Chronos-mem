"""Verification for the tool_brittleness analytical view (M1 follow-up).

Logs actions across several tools with known success/failure mixes, then
confirms tool_brittleness() returns the right counts, failure rates, and
most-brittle-first ordering. Run with CHRONOS_DSN set.
"""

import asyncio
import os
import sys

from chronos_mem import ChronosClient, OutcomeStatus


async def _log(db, plan_id, tool, status, agent="agent-analytics"):
    action = await db.log_action(plan_id=plan_id, tool_name=tool)
    await db.log_outcome(action_id=action.id, status=status)


async def main() -> int:
    dsn = os.environ["CHRONOS_DSN"]
    async with ChronosClient(dsn=dsn) as db:
        plan = await db.create_plan(agent_id="agent-analytics", goal="exercise tools")

        # flaky.tool: 1 success, 3 failures  -> failure_rate 0.75
        await _log(db, plan.id, "flaky.tool", OutcomeStatus.SUCCESS)
        for _ in range(3):
            await _log(db, plan.id, "flaky.tool", OutcomeStatus.FAILURE)
        # solid.tool: 4 success, 0 failures  -> failure_rate 0.0
        for _ in range(4):
            await _log(db, plan.id, "solid.tool", OutcomeStatus.SUCCESS)
        # mixed.tool: 1 success, 1 error, 1 partial -> failure_rate 0.3333
        await _log(db, plan.id, "mixed.tool", OutcomeStatus.SUCCESS)
        await _log(db, plan.id, "mixed.tool", OutcomeStatus.ERROR)
        await _log(db, plan.id, "mixed.tool", OutcomeStatus.PARTIAL)

        rows = await db.tool_brittleness()
        by_tool = {r.tool_name: r for r in rows}

        assert by_tool["flaky.tool"].total_calls == 4
        assert by_tool["flaky.tool"].failures == 3
        assert abs(by_tool["flaky.tool"].failure_rate - 0.75) < 1e-6
        assert by_tool["solid.tool"].failures == 0
        assert abs(by_tool["solid.tool"].failure_rate - 0.0) < 1e-6
        assert by_tool["mixed.tool"].partials == 1
        assert abs(by_tool["mixed.tool"].failure_rate - 0.3333) < 1e-3
        print("[ok] counts and failure rates correct")

        # Most-brittle-first ordering.
        ranked = [r.tool_name for r in rows]
        assert ranked.index("flaky.tool") < ranked.index("mixed.tool") < ranked.index("solid.tool"), ranked
        print(f"[ok] ranked most-brittle first: {ranked}")

    print("\nALL ANALYTICS CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
