"""chronos-mem debug dashboard — a one-page causal timeline tracer.

Pick a plan and see its goal DAG rendered as a flowchart, with failed nodes
highlighted in red, the ancestor decomposition that led there, and a table of
every failed action. Reads through the SDK's query_causality.

Run:
    pip install -r dashboard/requirements.txt
    CHRONOS_DSN="postgresql://chronos:chronos@localhost:5432/chronos_mem" \
        streamlit run dashboard/app.py
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import streamlit as st

from chronos_mem import BestIntervention, ChronosClient, CausalTrace
from render import build_dot

_DSN_ENV = "CHRONOS_DSN"

# Pick recent root goals so the user has something to click without copying UUIDs.
_RECENT_ROOTS_SQL = """
SELECT id, agent_id, goal, status, created_at
FROM plans
WHERE parent_plan_id IS NULL
ORDER BY created_at DESC
LIMIT 50;
"""


async def _load_recent_roots(dsn: str) -> list[dict[str, Any]]:
    async with ChronosClient(dsn=dsn) as db:
        return await db._fetch(_RECENT_ROOTS_SQL, {})


async def _load_trace(dsn: str, plan_id: str) -> CausalTrace:
    async with ChronosClient(dsn=dsn) as db:
        return await db.query_causality(plan_id)


async def _load_suggestions(
    dsn: str, error_types: list[str]
) -> dict[str, BestIntervention | None]:
    """For each distinct failure, pull the historically best fix (if any)."""
    async with ChronosClient(dsn=dsn) as db:
        return {et: await db.get_best_intervention(et) for et in error_types}


def _run(coro: Any) -> Any:
    """Drive an async SDK call from Streamlit's synchronous script context."""
    return asyncio.run(coro)


def main() -> None:
    st.set_page_config(page_title="chronos-mem · causal tracer", layout="wide")
    st.title("chronos-mem — causal timeline tracer")
    st.caption("Trace an agent's goal DAG. Failed plan nodes are highlighted in red.")

    dsn = st.sidebar.text_input(
        "Database DSN",
        value=os.getenv(_DSN_ENV, "postgresql://chronos:chronos@localhost:5432/chronos_mem"),
    )

    # Plan picker: recent root goals + a free-text override for any plan id.
    plan_id: str | None = None
    try:
        roots = _run(_load_recent_roots(dsn))
    except Exception as exc:  # connection problems, etc.
        st.error(f"Could not connect to the database: {exc}")
        st.stop()

    if roots:
        labels = {
            f"{r['goal']}  ·  {r['status']}  ·  {r['id']}": str(r["id"]) for r in roots
        }
        choice = st.sidebar.selectbox("Recent root goals", list(labels.keys()))
        plan_id = labels[choice]
    else:
        st.sidebar.info("No plans yet. Log some agent activity first.")

    override = st.sidebar.text_input("…or trace a specific plan id", value="")
    if override.strip():
        plan_id = override.strip()

    if not plan_id:
        st.stop()

    try:
        trace = _run(_load_trace(dsn, plan_id))
    except LookupError:
        st.warning(f"No plan found with id {plan_id}")
        st.stop()
    except Exception as exc:
        st.error(f"Trace failed: {exc}")
        st.stop()

    # Headline metrics.
    c1, c2, c3 = st.columns(3)
    c1.metric("Plan nodes", len(trace.subtree))
    c2.metric("Failed nodes", len(trace.failed_nodes))
    c3.metric("Failed actions", len(trace.failed_actions))

    # Ancestor breadcrumb.
    if trace.ancestors:
        crumb = " → ".join(p.goal for p in trace.ancestors)
        st.markdown(f"**Goal path:** {crumb} → *(traced node)*")

    # The DAG flowchart — failed nodes red.
    st.subheader("Causal graph")
    st.graphviz_chart(build_dot(trace), use_container_width=True)

    # Failed-action detail table — the "what broke and why" view, with the
    # historically best fix suggested for each failure (the self-correct loop).
    if trace.failed_actions:
        st.subheader("Failures & suggested fixes")
        # Look up the best past intervention per distinct error. The error text
        # on the outcome is used as the intervention error_type lookup key.
        errors = [
            (a.outcome.error if a.outcome else "") or "" for a in trace.failed_actions
        ]
        distinct = sorted({e for e in errors if e})
        suggestions = _run(_load_suggestions(dsn, distinct)) if distinct else {}

        def _suggest(err: str) -> str:
            best: BestIntervention | None = suggestions.get(err)
            if best is None:
                return "— no past fix on record —"
            return f"{best.strategy.value.upper()} (worked {best.success_count}×)"

        st.table(
            [
                {
                    "tool": a.action.tool_name,
                    "status": a.outcome.status.value if a.outcome else "—",
                    "error": (a.outcome.error if a.outcome else "") or "",
                    "suggested fix": _suggest((a.outcome.error if a.outcome else "") or ""),
                }
                for a in trace.failed_actions
            ]
        )
    else:
        st.success("No failures in this trace.")


if __name__ == "__main__":
    main()
