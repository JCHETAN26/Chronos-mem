"""Tracking API — the developer-facing write surface of chronos-mem.

Implemented as a mixin so the connection-pool machinery (client.py) and the
agent-facing verbs (here) stay in separate, single-purpose files. ``ChronosClient``
inherits this mixin and supplies ``_fetchrow``.

Every method issues a single ``INSERT ... RETURNING *`` and validates the row
straight into the matching Pydantic model — one round trip, fully typed.
"""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from psycopg.types.json import Jsonb
from pydantic import validate_call

from .models import (
    Action,
    Intervention,
    InterventionStrategy,
    Outcome,
    OutcomeStatus,
    Plan,
    PlanStatus,
)


class _RowFetcher(Protocol):
    """Structural contract the mixin needs from its host class."""

    async def _fetchrow(self, query: str, params: tuple[Any, ...]) -> dict[str, Any]: ...


# Validate caller-supplied argument types against the annotations *before* any
# DB round trip — bad types (e.g. an int where a str is required) raise a
# pydantic.ValidationError client-side instead of wasting a connection. `self`
# is intentionally left unannotated so validate_call skips it.
class TrackingMixin:
    """create_plan / log_action / log_outcome / log_intervention — agent write verbs."""

    @validate_call
    async def create_plan(
        self,
        agent_id: str,
        goal: str,
        *,
        parent_plan_id: UUID | str | None = None,
        status: PlanStatus | str = PlanStatus.PENDING,
        metadata: dict[str, Any] | None = None,
    ) -> Plan:
        """Create a plan node. ``parent_plan_id=None`` makes it a root goal."""
        status_value = status.value if isinstance(status, PlanStatus) else status
        row = await self._fetchrow(
            """
            INSERT INTO plans (agent_id, parent_plan_id, goal, status, metadata)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING *
            """,
            (agent_id, parent_plan_id, goal, status_value, Jsonb(metadata or {})),
        )
        return Plan.model_validate(row)

    @validate_call
    async def log_action(
        self,
        plan_id: UUID | str,
        tool_name: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> Action:
        """Record a raw tool execution under a plan node."""
        row = await self._fetchrow(
            """
            INSERT INTO actions (plan_id, tool_name, payload)
            VALUES (%s, %s, %s)
            RETURNING *
            """,
            (plan_id, tool_name, Jsonb(payload or {})),
        )
        return Action.model_validate(row)

    @validate_call
    async def log_outcome(
        self,
        action_id: UUID | str,
        status: OutcomeStatus | str,
        *,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> Outcome:
        """Record the causal verdict for an action. One outcome per action."""
        status_value = status.value if isinstance(status, OutcomeStatus) else status
        row = await self._fetchrow(
            """
            INSERT INTO outcomes (action_id, status, result, error)
            VALUES (%s, %s, %s, %s)
            RETURNING *
            """,
            (action_id, status_value, Jsonb(result or {}), error),
        )
        return Outcome.model_validate(row)

    @validate_call
    async def log_intervention(
        self,
        outcome_id: UUID | str,
        error_type: str,
        strategy: InterventionStrategy | str,
        succeeded: bool,
        *,
        agent_id: str,
        details: dict[str, Any] | None = None,
    ) -> Intervention:
        """Record a post-failure decision (and whether it worked) for an outcome.

        ``error_type`` is the categorical key that get_best_intervention ranks on.
        """
        strategy_value = (
            strategy.value if isinstance(strategy, InterventionStrategy) else strategy
        )
        row = await self._fetchrow(
            """
            INSERT INTO interventions
                (agent_id, outcome_id, error_type, strategy, succeeded, details)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (agent_id, outcome_id, error_type, strategy_value, succeeded,
             Jsonb(details or {})),
        )
        return Intervention.model_validate(row)
