-- db/migrations/002_tool_brittleness_view.sql
-- chronos-mem — analytical view: tool brittleness (Milestone 1, follow-up)
--
-- Which tools fail most? This view aggregates every resolved action by tool,
-- exposing call volume, success/failure counts, and a failure_rate so an
-- operator (or the dashboard) can rank the most brittle tools at a glance.
--
-- Only actions that have an outcome are counted (an action without a logged
-- outcome isn't yet a success or a failure). Consumers should ORDER BY
-- failure_rate DESC, total_calls DESC — a view does not guarantee row order.
--
-- Idempotent: CREATE OR REPLACE. Apply after 001:
--   psql "$CHRONOS_DSN" -f db/migrations/002_tool_brittleness_view.sql

BEGIN;

CREATE OR REPLACE VIEW tool_brittleness AS
SELECT
    a.tool_name,
    count(*)                                                AS total_calls,
    count(*) FILTER (WHERE o.status = 'success')            AS successes,
    count(*) FILTER (WHERE o.status IN ('failure', 'error')) AS failures,
    count(*) FILTER (WHERE o.status = 'partial')            AS partials,
    -- failure_rate in [0,1], rounded to 4 dp. nullif guards against /0 (a
    -- group always has >=1 row here, but keep it defensive).
    round(
        count(*) FILTER (WHERE o.status IN ('failure', 'error'))::numeric
        / nullif(count(*), 0),
        4
    )                                                       AS failure_rate,
    max(o.created_at)                                       AS last_seen
FROM actions a
JOIN outcomes o ON o.action_id = a.id
GROUP BY a.tool_name;

COMMIT;
