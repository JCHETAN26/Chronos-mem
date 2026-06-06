-- db/queries/causality.sql
-- chronos-mem — causal tracing queries (Milestone 3)
--
-- These are the canonical, reviewed forms of the recursive CTEs the SDK
-- embeds in chronos_mem/causality.py. Kept here as the source of truth and
-- for ad-hoc psql debugging. The single bind parameter ($1) is the plan_id
-- being traced.
--
-- Why recursive CTEs: the plan DAG is stored as self-referencing rows
-- (plans.parent_plan_id -> plans.id). Walking it in SQL — rather than issuing
-- one query per level from the client — keeps a full trace to a single round
-- trip. Both directions are backed by indexes:
--   * downward walk uses idx_plans_parent_plan_id
--   * upward walk uses the plans primary key
-- so each step is an index lookup and the whole trace stays well under the
-- 5ms target for realistic graph sizes.

-- ===========================================================================
-- (A) SUBTREE — walk DOWN from the target plan to every descendant node,
--     joined to its actions and their outcomes. One row per action
--     (plans with no actions still appear once, via LEFT JOIN).
--     This is the "everything that happened under this goal" view that
--     powers the dashboard and surfaces where failures occurred.
-- ===========================================================================
WITH RECURSIVE subtree AS (
    -- anchor: the traced node itself, at depth 0
    SELECT
        p.id,
        p.parent_plan_id,
        p.agent_id,
        p.goal,
        p.status,
        p.metadata,
        p.created_at,
        0 AS depth
    FROM plans p
    WHERE p.id = $1

    UNION ALL

    -- recurse: children of nodes already in the subtree
    SELECT
        c.id,
        c.parent_plan_id,
        c.agent_id,
        c.goal,
        c.status,
        c.metadata,
        c.created_at,
        s.depth + 1
    FROM plans c
    JOIN subtree s ON c.parent_plan_id = s.id
)
SELECT
    s.id                AS plan_id,
    s.parent_plan_id    AS parent_plan_id,
    s.agent_id          AS agent_id,
    s.goal              AS goal,
    s.status            AS plan_status,
    s.metadata          AS plan_metadata,
    s.created_at        AS plan_created_at,
    s.depth             AS depth,
    a.id                AS action_id,
    a.tool_name         AS tool_name,
    a.payload           AS action_payload,
    a.created_at        AS action_created_at,
    o.id                AS outcome_id,
    o.status            AS outcome_status,
    o.result            AS outcome_result,
    o.error             AS outcome_error,
    o.created_at        AS outcome_created_at
FROM subtree s
LEFT JOIN actions  a ON a.plan_id   = s.id
LEFT JOIN outcomes o ON o.action_id = a.id
ORDER BY s.depth ASC, s.created_at ASC, a.created_at ASC NULLS FIRST;

-- ===========================================================================
-- (B) ANCESTORS — walk UP from the target plan to the root goal. This is the
--     "what decomposition led here" path used to explain a failure backwards.
--     Returned root-first (outermost goal at the top), excluding the node
--     itself.
-- ===========================================================================
WITH RECURSIVE ancestors AS (
    -- anchor: the traced node, at height 0
    SELECT
        p.id,
        p.parent_plan_id,
        p.agent_id,
        p.goal,
        p.status,
        p.metadata,
        p.created_at,
        0 AS height
    FROM plans p
    WHERE p.id = $1

    UNION ALL

    -- recurse: the parent of each node already collected
    SELECT
        p.id,
        p.parent_plan_id,
        p.agent_id,
        p.goal,
        p.status,
        p.metadata,
        p.created_at,
        a.height + 1
    FROM plans p
    JOIN ancestors a ON p.id = a.parent_plan_id
)
SELECT
    id              AS plan_id,
    parent_plan_id  AS parent_plan_id,
    agent_id        AS agent_id,
    goal            AS goal,
    status          AS plan_status,
    metadata        AS plan_metadata,
    created_at      AS plan_created_at,
    height          AS height
FROM ancestors
WHERE id <> $1          -- exclude the traced node itself
ORDER BY height DESC;   -- root goal first
