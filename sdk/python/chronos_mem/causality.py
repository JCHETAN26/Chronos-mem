"""Causal tracing — the debugging read layer of chronos-mem.

``query_causality(plan_id)`` explains a point in an agent's execution by walking
the plan DAG in both directions with two recursive CTEs (one round trip each):

  * DOWN  — the subtree of descendant plans, each with its actions + outcomes,
            so you can see everything that happened under a goal and where it
            broke.
  * UP    — the ancestor path back to the root goal, so a failure can be read
            backwards through the decomposition that produced it.

The canonical SQL lives in db/queries/causality.sql; the embedded copies below
are kept byte-for-byte equivalent. Both walks are index-backed
(idx_plans_parent_plan_id downward, the primary key upward), keeping a trace to
a single statement per direction and well inside the sub-5ms target.

Implemented as a mixin; ChronosClient supplies ``_fetch``.
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol
from uuid import UUID

from .models import (
    Action,
    ActionTrace,
    CausalNode,
    CausalTrace,
    Outcome,
    Plan,
)

# --- Embedded queries (see db/queries/causality.sql) -----------------------

_SUBTREE_SQL = """
WITH RECURSIVE subtree AS (
    SELECT p.id, p.parent_plan_id, p.agent_id, p.goal, p.status, p.metadata,
           p.created_at, 0 AS depth
    FROM plans p
    WHERE p.id = %(plan_id)s
    UNION ALL
    SELECT c.id, c.parent_plan_id, c.agent_id, c.goal, c.status, c.metadata,
           c.created_at, s.depth + 1
    FROM plans c
    JOIN subtree s ON c.parent_plan_id = s.id
)
SELECT
    s.id            AS plan_id,
    s.parent_plan_id,
    s.agent_id,
    s.goal,
    s.status        AS plan_status,
    s.metadata      AS plan_metadata,
    s.created_at    AS plan_created_at,
    s.depth,
    a.id            AS action_id,
    a.tool_name,
    a.payload       AS action_payload,
    a.created_at    AS action_created_at,
    o.id            AS outcome_id,
    o.status        AS outcome_status,
    o.result        AS outcome_result,
    o.error         AS outcome_error,
    o.created_at    AS outcome_created_at
FROM subtree s
LEFT JOIN actions  a ON a.plan_id   = s.id
LEFT JOIN outcomes o ON o.action_id = a.id
ORDER BY s.depth ASC, s.created_at ASC, a.created_at ASC NULLS FIRST;
"""

_ANCESTORS_SQL = """
WITH RECURSIVE ancestors AS (
    SELECT p.id, p.parent_plan_id, p.agent_id, p.goal, p.status, p.metadata,
           p.created_at, 0 AS height
    FROM plans p
    WHERE p.id = %(plan_id)s
    UNION ALL
    SELECT p.id, p.parent_plan_id, p.agent_id, p.goal, p.status, p.metadata,
           p.created_at, a.height + 1
    FROM plans p
    JOIN ancestors a ON p.id = a.parent_plan_id
)
SELECT id AS plan_id, parent_plan_id, agent_id, goal, status AS plan_status,
       metadata AS plan_metadata, created_at AS plan_created_at, height
FROM ancestors
WHERE id <> %(plan_id)s
ORDER BY height DESC;
"""


class _Fetcher(Protocol):
    def _cursor(self) -> AbstractAsyncContextManager[Any]: ...


def _plan_from_row(row: dict[str, Any]) -> Plan:
    """Rebuild a Plan from a CTE row's aliased plan_* columns."""
    return Plan.model_validate(
        {
            "id": row["plan_id"],
            "agent_id": row["agent_id"],
            "parent_plan_id": row["parent_plan_id"],
            "goal": row["goal"],
            "status": row["plan_status"],
            "metadata": row["plan_metadata"],
            "created_at": row["plan_created_at"],
            # updated_at isn't needed for a trace view; mirror created_at so the
            # required field validates without a second column in the CTE.
            "updated_at": row["plan_created_at"],
        }
    )


class CausalityMixin:
    """query_causality — backwards/forwards causal trace over the plan DAG."""

    async def query_causality(self: _Fetcher, plan_id: UUID | str) -> CausalTrace:
        """Return the full causal context of ``plan_id``.

        Runs the subtree (downward) and ancestor (upward) CTEs on a single
        pooled connection — one checkout, one consistent snapshot — and
        assembles a typed :class:`CausalTrace`. Raises ``LookupError`` if the
        plan is absent.
        """
        params = {"plan_id": str(plan_id)}
        async with self._cursor() as cur:
            await cur.execute(_SUBTREE_SQL, params)
            subtree_rows = await cur.fetchall()
            if not subtree_rows:
                raise LookupError(f"No plan found with id {plan_id!r}")
            await cur.execute(_ANCESTORS_SQL, params)
            ancestor_rows = await cur.fetchall()

        # Group the flat (plan x action) rows into one CausalNode per plan,
        # preserving the SQL ordering (depth, then chronological).
        nodes: dict[Any, CausalNode] = {}
        for row in subtree_rows:
            pid = row["plan_id"]
            node = nodes.get(pid)
            if node is None:
                node = CausalNode(plan=_plan_from_row(row), depth=row["depth"], actions=[])
                nodes[pid] = node

            if row["action_id"] is None:
                continue  # plan node with no actions (LEFT JOIN null row)

            action = Action.model_validate(
                {
                    "id": row["action_id"],
                    "plan_id": pid,
                    "tool_name": row["tool_name"],
                    "payload": row["action_payload"],
                    "created_at": row["action_created_at"],
                }
            )
            outcome = None
            if row["outcome_id"] is not None:
                outcome = Outcome.model_validate(
                    {
                        "id": row["outcome_id"],
                        "action_id": row["action_id"],
                        "status": row["outcome_status"],
                        "result": row["outcome_result"],
                        "error": row["outcome_error"],
                        "created_at": row["outcome_created_at"],
                    }
                )
            node.actions.append(ActionTrace(action=action, outcome=outcome))

        ancestors = [_plan_from_row(r) for r in ancestor_rows]

        return CausalTrace(
            plan_id=UUID(str(plan_id)),
            ancestors=ancestors,
            subtree=list(nodes.values()),
        )
