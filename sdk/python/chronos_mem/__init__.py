"""chronos-mem — structured memory & causal debugging engine for AI agents.

Public surface:

    from chronos_mem import ChronosClient

    async with ChronosClient(dsn="postgresql://...") as db:
        plan = await db.create_plan(agent_id="agent-1", goal="Book a vacation")
        action = await db.log_action(plan_id=plan.id, tool_name="flights.search")
        await db.log_outcome(action_id=action.id, status="success")
"""

from .client import ChronosClient
from .models import (
    Action,
    Intervention,
    InterventionStrategy,
    Memory,
    Outcome,
    OutcomeStatus,
    Plan,
    PlanStatus,
)

__all__ = [
    "ChronosClient",
    "Memory",
    "Plan",
    "Action",
    "Outcome",
    "Intervention",
    "PlanStatus",
    "OutcomeStatus",
    "InterventionStrategy",
]

__version__ = "0.1.0"
