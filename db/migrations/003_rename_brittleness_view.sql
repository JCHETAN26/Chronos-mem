-- db/migrations/003_rename_brittleness_view.sql
-- chronos-mem — rename the tool-brittleness view to its documented name.
--
-- 002 created the view as `tool_brittleness`; the production-readiness checklist
-- refers to it as `view_tool_brittleness_analysis`. Rename so the name matches
-- the spec. Pure rename — definition unchanged.
--
-- Apply after 002:
--   psql "$CHRONOS_DSN" -f db/migrations/003_rename_brittleness_view.sql

BEGIN;

ALTER VIEW IF EXISTS tool_brittleness RENAME TO view_tool_brittleness_analysis;

COMMIT;
