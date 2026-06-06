"""Intervention engine — the self-correction read layer of chronos-mem.

``get_best_intervention(error_type)`` answers "how was this kind of failure
fixed before?" by ranking past *successful* interventions for that error type
and returning the winner. An agent can call this the moment it logs a failure
and immediately retry with a strategy that has worked.

The lookup is a single grouped aggregate over the (error_type, succeeded)
composite index (idx_interventions_lookup), keeping it inside the sub-5ms
target. Canonical SQL: db/queries/interventions.sql.

Implemented as a mixin; ChronosClient supplies ``_fetch``.
"""

from __future__ import annotations

from typing import Any, Protocol

from .models import BestIntervention

# Rank strategies that have resolved this error type before: most successes
# first, then most recently proven.
_BEST_INTERVENTION_SQL = """
SELECT
    error_type,
    strategy,
    count(*)        AS success_count,
    max(created_at) AS last_used
FROM interventions
WHERE error_type = %(error_type)s
  AND succeeded = TRUE
GROUP BY error_type, strategy
ORDER BY success_count DESC, last_used DESC
LIMIT 1;
"""


class _Fetcher(Protocol):
    async def _fetch(self, query: str, params: Any) -> list[dict[str, Any]]: ...


class InterventionMixin:
    """get_best_intervention — query past fixes for real-time self-correction."""

    async def get_best_intervention(
        self: _Fetcher, error_type: str
    ) -> BestIntervention | None:
        """Return the most successful past strategy for ``error_type``.

        ``None`` if no successful intervention has ever been logged for it.
        """
        rows = await self._fetch(_BEST_INTERVENTION_SQL, {"error_type": error_type})
        if not rows:
            return None
        return BestIntervention.model_validate(rows[0])
