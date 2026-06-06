"""Pure rendering helpers for the chronos-mem debug dashboard.

Kept free of Streamlit so the graph-building logic is unit-testable on its own.
``build_dot`` turns a :class:`chronos_mem.CausalTrace` into a Graphviz DOT
string; the Streamlit app (app.py) just hands the result to st.graphviz_chart.
"""

from __future__ import annotations

from chronos_mem import CausalNode, CausalTrace, PlanStatus

# Fill colours per plan status. Failed nodes are forced red regardless of
# status so a failure is impossible to miss in the graph.
_FAILED_FILL = "#f8b4b4"   # red — a failed node or a node with a failed action
_FAILED_EDGE = "#b91c1c"
_STATUS_FILL: dict[PlanStatus, str] = {
    PlanStatus.PENDING: "#e5e7eb",      # grey
    PlanStatus.IN_PROGRESS: "#bfdbfe",  # blue
    PlanStatus.COMPLETED: "#bbf7d0",    # green
    PlanStatus.FAILED: _FAILED_FILL,
    PlanStatus.ABANDONED: "#d1d5db",    # darker grey
}


def node_fill(node: CausalNode) -> str:
    """Fill colour for a node: red if it (or any of its actions) failed."""
    if node.failed:
        return _FAILED_FILL
    return _STATUS_FILL.get(node.plan.status, "#e5e7eb")


def _escape(text: str) -> str:
    """Escape a label for DOT (quotes and newlines)."""
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _node_label(node: CausalNode) -> str:
    n_actions = len(node.actions)
    n_failed = sum(1 for a in node.actions if a.failed)
    parts = [node.plan.goal, f"[{node.plan.status.value}]"]
    if n_actions:
        suffix = f"{n_actions} action(s)"
        if n_failed:
            suffix += f", {n_failed} failed"
        parts.append(suffix)
    return _escape("\n".join(parts))


def build_dot(trace: CausalTrace) -> str:
    """Build a Graphviz DOT digraph for a causal trace.

    Nodes are the traced plan's subtree (failed ones filled red). The ancestor
    path above the traced node is drawn as a dashed breadcrumb leading into it.
    """
    lines: list[str] = [
        "digraph causal {",
        "  rankdir=TB;",
        '  node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=11];',
        '  edge [color="#9ca3af"];',
    ]

    subtree_ids = {str(node.plan.id) for node in trace.subtree}

    # Ancestor breadcrumb (dashed, grey) — root goal down to the traced node.
    ancestor_ids = [str(p.id) for p in trace.ancestors]
    for plan in trace.ancestors:
        label = _escape(f"{plan.goal}\n[{plan.status.value}]")
        lines.append(
            f'  "{plan.id}" [label="{label}", fillcolor="#f3f4f6", '
            f'style="rounded,filled,dashed"];'
        )
    chain = ancestor_ids + [str(trace.plan_id)]
    for parent, child in zip(chain, chain[1:]):
        lines.append(f'  "{parent}" -> "{child}" [style=dashed];')

    # Subtree nodes.
    for node in trace.subtree:
        pid = str(node.plan.id)
        fill = node_fill(node)
        attrs = f'label="{_node_label(node)}", fillcolor="{fill}"'
        if node.failed:
            attrs += f', color="{_FAILED_EDGE}", penwidth=2'
        lines.append(f'  "{pid}" [{attrs}];')

    # Subtree edges (parent -> child) — only where both ends are in the subtree.
    for node in trace.subtree:
        parent = node.plan.parent_plan_id
        if parent is not None and str(parent) in subtree_ids:
            edge_attr = ""
            if node.failed:
                edge_attr = f' [color="{_FAILED_EDGE}", penwidth=2]'
            lines.append(f'  "{parent}" -> "{node.plan.id}"{edge_attr};')

    lines.append("}")
    return "\n".join(lines)
