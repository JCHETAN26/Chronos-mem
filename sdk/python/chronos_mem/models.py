"""Pydantic v2 models mirroring the chronos-mem SQL schema.

One model per relational pillar. These are the typed values returned by the
tracking API; field names and types match db/migrations/001_init_chronos_schema.sql
exactly so a ``RETURNING *`` row validates straight into the model.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PlanStatus(str, Enum):
    """Lifecycle of a plan node — mirrors the SQL ``plan_status`` enum."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ABANDONED = "abandoned"


class OutcomeStatus(str, Enum):
    """Terminal verdict for an action — mirrors the SQL ``outcome_status`` enum."""

    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    ERROR = "error"


class InterventionStrategy(str, Enum):
    """Post-failure operational decision — mirrors ``intervention_strategy``."""

    RETRY = "retry"
    ESCALATE = "escalate"
    PIVOT = "pivot"
    ROLLBACK = "rollback"
    ABORT = "abort"


class _Base(BaseModel):
    # Tolerate extra columns (e.g. a future migration adds a field) without
    # breaking older clients; validate enums from their raw string values.
    model_config = ConfigDict(extra="ignore", use_enum_values=False)


class Memory(_Base):
    """Pillar 1 — a long-term episodic fact / preference."""

    id: UUID
    agent_id: str
    content: str
    # The raw embedding is intentionally not surfaced by default (large, rarely
    # needed by callers). Recall returns content + similarity, not the vector.
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class Plan(_Base):
    """Pillar 2 — a node in the agent's hierarchical goal DAG."""

    id: UUID
    agent_id: str
    parent_plan_id: UUID | None = None
    goal: str
    status: PlanStatus
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class Action(_Base):
    """Pillar 3 — a single raw tool execution under a plan node."""

    id: UUID
    plan_id: UUID
    tool_name: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class Outcome(_Base):
    """Pillar 4 — the causal success/failure verdict for an action."""

    id: UUID
    action_id: UUID
    status: OutcomeStatus
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    created_at: datetime


class Intervention(_Base):
    """Pillar 5 — a logged post-failure decision and whether it worked."""

    id: UUID
    agent_id: str
    outcome_id: UUID
    error_type: str
    strategy: InterventionStrategy
    succeeded: bool
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class BestIntervention(_Base):
    """The historically most-successful strategy for an error type.

    Returned by get_best_intervention(): the strategy with the most past
    successes for a given error_type, so an agent can self-correct.
    """

    error_type: str
    strategy: InterventionStrategy
    success_count: int
    last_used: datetime


# --- Causal trace composites (Milestone 3) ---------------------------------
# Assembled by query_causality() from the recursive-CTE rows. These are read
# views over the pillars, not tables of their own.

# Outcome states that count as a failure when hunting for root causes.
FAILURE_STATES: frozenset[OutcomeStatus] = frozenset(
    {OutcomeStatus.FAILURE, OutcomeStatus.ERROR}
)


class ActionTrace(_Base):
    """An action paired with its outcome (if one has been logged yet)."""

    action: Action
    outcome: Outcome | None = None

    @property
    def failed(self) -> bool:
        """True when the action has a terminal failure/error verdict."""
        return self.outcome is not None and self.outcome.status in FAILURE_STATES


class CausalNode(_Base):
    """A plan node within a trace, with its actions and their outcomes.

    ``depth`` is the distance below the traced plan (0 == the traced node).
    """

    plan: Plan
    depth: int
    actions: list[ActionTrace] = Field(default_factory=list)

    @property
    def failed(self) -> bool:
        """True if the plan node itself failed or any of its actions failed."""
        return self.plan.status == PlanStatus.FAILED or any(a.failed for a in self.actions)


class CausalTrace(_Base):
    """The full causal context of a plan: its ancestry and its subtree.

    - ``ancestors``: the goal-decomposition path from the root down to (but
      excluding) the traced node — the "backwards" explanation of how the
      agent arrived here.
    - ``subtree``: the traced node (depth 0) plus every descendant, each with
      its actions and outcomes — everything that happened under this goal.
    """

    plan_id: UUID
    ancestors: list[Plan] = Field(default_factory=list)
    subtree: list[CausalNode] = Field(default_factory=list)

    @property
    def root(self) -> CausalNode:
        """The traced node itself (depth 0)."""
        return self.subtree[0]

    @property
    def failed_actions(self) -> list[ActionTrace]:
        """Every failed/errored action anywhere in the subtree."""
        return [a for node in self.subtree for a in node.actions if a.failed]

    @property
    def failed_nodes(self) -> list[CausalNode]:
        """Every subtree plan node that failed."""
        return [node for node in self.subtree if node.failed]

    @property
    def has_failures(self) -> bool:
        return bool(self.failed_nodes)
