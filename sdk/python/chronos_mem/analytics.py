"""Analytics — read accessors over chronos-mem's analytical views.

``tool_brittleness()`` surfaces the tool_brittleness view (db/migrations/
002_tool_brittleness_view.sql): which tools fail most, ranked. Useful for the
dashboard and for an operator deciding which integrations to harden.

Implemented as a mixin; ChronosClient supplies ``_fetch``.
"""

from __future__ import annotations

from typing import Any, Protocol

from .models import ToolBrittleness

# Order most-brittle first; the view itself does not guarantee row order.
_TOOL_BRITTLENESS_SQL = """
SELECT tool_name, total_calls, successes, failures, partials, failure_rate, last_seen
FROM tool_brittleness
ORDER BY failure_rate DESC, total_calls DESC
LIMIT %(limit)s;
"""


class _Fetcher(Protocol):
    async def _fetch(self, query: str, params: Any) -> list[dict[str, Any]]: ...


class AnalyticsMixin:
    """tool_brittleness — rank tools by how often they fail."""

    async def tool_brittleness(
        self: _Fetcher, limit: int = 50
    ) -> list[ToolBrittleness]:
        """Return per-tool failure profiles, most brittle first."""
        rows = await self._fetch(_TOOL_BRITTLENESS_SQL, {"limit": limit})
        return [ToolBrittleness.model_validate(r) for r in rows]
