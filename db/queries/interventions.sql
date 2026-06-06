-- db/queries/interventions.sql
-- chronos-mem — intervention engine queries (Milestone 3)
--
-- Canonical form of the lookup the SDK embeds in chronos_mem/interventions.py.
-- The bind parameter ($1) is the error_type being self-corrected.
--
-- get_best_intervention(error_type): of every strategy that has SUCCEEDED for
-- this class of error before, return the one proven most often (ties broken by
-- most recent). This is what lets an agent react to a fresh failure with a fix
-- that already worked.
--
-- Backed by idx_interventions_lookup (error_type, succeeded): the WHERE clause
-- is a pure index range, so the aggregate touches only the matching rows and
-- stays well under the 5ms target.

SELECT
    error_type,
    strategy,
    count(*)        AS success_count,
    max(created_at) AS last_used
FROM interventions
WHERE error_type = $1
  AND succeeded = TRUE
GROUP BY error_type, strategy
ORDER BY success_count DESC, last_used DESC
LIMIT 1;
