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
