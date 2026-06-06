-- db/migrations/001_init_chronos_schema.sql
-- chronos-mem — core schema (Milestone 1)
--
-- The five relational pillars of an agent's brain:
--   memories      — long-term episodic facts / preferences (pgvector + text)
--   plans         — hierarchical DAGs of goal breakdowns over time
--   actions       — raw tool executions (inputs/params/payloads as JSONB)
--   outcomes      — causal success/failure states linked to actions
--   interventions — post-failure decision log (retry/escalate/pivot) + success
--
-- Design rules:
--   * Strict foreign keys; deletes cascade down the causal chain.
--   * Every traversal/lookup path is backed by an index (sub-5ms target).
--   * Timestamps are UTC (timestamptz), defaulting to now().
--
-- Applied automatically on first cluster init by docker-compose, or by hand:
--   psql "$CHRONOS_DSN" -f db/migrations/001_init_chronos_schema.sql

BEGIN;

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS vector;      -- pgvector: embeddings on memories
CREATE EXTENSION IF NOT EXISTS pgcrypto;    -- gen_random_uuid()

-- ---------------------------------------------------------------------------
-- Enumerated states
-- ---------------------------------------------------------------------------
-- Lifecycle of a plan node as the agent works through its goal DAG.
CREATE TYPE plan_status AS ENUM (
    'pending',
    'in_progress',
    'completed',
    'failed',
    'abandoned'
);

-- Terminal causal verdict for an action.
CREATE TYPE outcome_status AS ENUM (
    'success',
    'failure',
    'partial',
    'error'
);

-- Operational decision an agent takes in response to a failure.
CREATE TYPE intervention_strategy AS ENUM (
    'retry',
    'escalate',
    'pivot',
    'rollback',
    'abort'
);

-- ---------------------------------------------------------------------------
-- Pillar 1: memories
-- Long-term episodic facts / preferences. Semantic recall via pgvector.
-- ---------------------------------------------------------------------------
CREATE TABLE memories (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id    TEXT        NOT NULL,           -- which agent owns this memory
    content     TEXT        NOT NULL,           -- the human-readable fact
    -- Embedding dimension is fixed at the schema level for index support.
    -- 1536 = OpenAI text-embedding-3-small. Change here + reindex to swap models.
    embedding   VECTOR(1536),
    metadata    JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Scope every recall to a single agent's memory space.
CREATE INDEX idx_memories_agent_id  ON memories (agent_id);
CREATE INDEX idx_memories_created_at ON memories (created_at DESC);
-- Approximate nearest-neighbour search over embeddings (cosine distance).
-- HNSW gives low-latency recall that fits the sub-5ms target at small/medium N.
CREATE INDEX idx_memories_embedding ON memories
    USING hnsw (embedding vector_cosine_ops);
-- Containment / filter queries on structured metadata.
CREATE INDEX idx_memories_metadata ON memories USING gin (metadata);

-- ---------------------------------------------------------------------------
-- Pillar 2: plans
-- Hierarchical DAG of goal breakdowns. parent_plan_id forms the edges.
-- ---------------------------------------------------------------------------
CREATE TABLE plans (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        TEXT        NOT NULL,
    -- Self-referencing edge: NULL parent == root goal. Deleting a parent
    -- cascades to its sub-plans (the whole subtree of the goal).
    parent_plan_id  UUID        REFERENCES plans (id) ON DELETE CASCADE,
    goal            TEXT        NOT NULL,        -- what this node is trying to achieve
    status          plan_status NOT NULL DEFAULT 'pending',
    metadata        JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Walk the DAG downward fast (children of a node) — used by the recursive
-- causal-trace CTE in Milestone 3.
CREATE INDEX idx_plans_parent_plan_id ON plans (parent_plan_id);
CREATE INDEX idx_plans_agent_id       ON plans (agent_id);
CREATE INDEX idx_plans_status         ON plans (status);

-- ---------------------------------------------------------------------------
-- Pillar 3: actions
-- Raw tool executions. The full tool call (name, inputs, params, payload)
-- lives in JSONB so the schema never blocks a new tool shape.
-- ---------------------------------------------------------------------------
CREATE TABLE actions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id     UUID        NOT NULL REFERENCES plans (id) ON DELETE CASCADE,
    tool_name   TEXT        NOT NULL,           -- which tool was invoked
    payload     JSONB       NOT NULL DEFAULT '{}'::jsonb,  -- inputs / params / raw call
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Fetch all actions for a plan node (causal trace + timeline rendering).
CREATE INDEX idx_actions_plan_id   ON actions (plan_id);
CREATE INDEX idx_actions_tool_name ON actions (tool_name);
CREATE INDEX idx_actions_payload   ON actions USING gin (payload);

-- ---------------------------------------------------------------------------
-- Pillar 4: outcomes
-- Causal success/failure of an action. One row per action (the verdict).
-- ---------------------------------------------------------------------------
CREATE TABLE outcomes (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- One outcome per action: the action's terminal verdict.
    action_id   UUID           NOT NULL UNIQUE REFERENCES actions (id) ON DELETE CASCADE,
    status      outcome_status NOT NULL,
    result      JSONB          NOT NULL DEFAULT '{}'::jsonb,  -- tool return / observation
    error       TEXT,                          -- failure detail, when status != success
    created_at  TIMESTAMPTZ    NOT NULL DEFAULT now()
);

CREATE INDEX idx_outcomes_action_id ON outcomes (action_id);
-- Hunt for failures fast — the entry point of any "why did this break?" trace.
CREATE INDEX idx_outcomes_status    ON outcomes (status);

-- ---------------------------------------------------------------------------
-- Pillar 5: interventions
-- Operational decision log: what the system did AFTER a failure (retry,
-- escalate, pivot, ...) and whether that fix worked. This is what lets an
-- agent query "how was this kind of error solved before?" and self-correct.
-- Hybrid JSONB-Relational: error_type/strategy/succeeded are relational (so
-- get_best_intervention can rank them), details is flexible workspace JSONB.
-- ---------------------------------------------------------------------------
CREATE TABLE interventions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id    TEXT                  NOT NULL,
    -- The failure this intervention responds to. Cascades with the outcome.
    outcome_id  UUID                  NOT NULL REFERENCES outcomes (id) ON DELETE CASCADE,
    -- Categorical class of failure (e.g. 'payment_declined'). The lookup key
    -- for get_best_intervention(error_type).
    error_type  TEXT                  NOT NULL,
    strategy    intervention_strategy NOT NULL,
    -- Did the intervention resolve the failure?
    succeeded   BOOLEAN               NOT NULL,
    details     JSONB                 NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ           NOT NULL DEFAULT now()
);

CREATE INDEX idx_interventions_outcome_id ON interventions (outcome_id);
CREATE INDEX idx_interventions_agent_id   ON interventions (agent_id);
-- Composite index powering get_best_intervention: filter by error_type +
-- succeeded, then rank strategies. Keeps the self-correct lookup sub-5ms.
CREATE INDEX idx_interventions_lookup ON interventions (error_type, succeeded);
CREATE INDEX idx_interventions_details ON interventions USING gin (details);

COMMIT;
