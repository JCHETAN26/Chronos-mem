"""Unit tests for the pure dashboard rendering (no DB, no Streamlit)."""

from datetime import datetime, timezone
from uuid import uuid4

from chronos_mem import (
    Action,
    ActionTrace,
    CausalNode,
    CausalTrace,
    Outcome,
    OutcomeStatus,
    Plan,
    PlanStatus,
)
from render import _FAILED_FILL, build_dot, node_fill

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _plan(pid, status, parent=None, goal="g"):
    return Plan(id=pid, agent_id="a", parent_plan_id=parent, goal=goal,
                status=status, metadata={}, created_at=_NOW, updated_at=_NOW)


def _failed_action():
    aid = uuid4()
    return ActionTrace(
        action=Action(id=aid, plan_id=uuid4(), tool_name="payments.charge",
                      payload={}, created_at=_NOW),
        outcome=Outcome(id=uuid4(), action_id=aid, status=OutcomeStatus.FAILURE,
                        result={}, error="declined", created_at=_NOW),
    )


def _build_trace():
    root_id, child_id = uuid4(), uuid4()
    root = CausalNode(plan=_plan(root_id, PlanStatus.IN_PROGRESS, goal="root"),
                      depth=0, actions=[])
    child = CausalNode(
        plan=_plan(child_id, PlanStatus.FAILED, parent=root_id, goal="charge card"),
        depth=1, actions=[_failed_action()],
    )
    ancestor = _plan(uuid4(), PlanStatus.IN_PROGRESS, goal="trip")
    return root_id, child_id, CausalTrace(
        plan_id=root_id, ancestors=[ancestor], subtree=[root, child],
    )


def test_failed_node_is_red():
    _, _, trace = _build_trace()
    failed = trace.subtree[1]
    assert failed.failed is True
    assert node_fill(failed) == _FAILED_FILL


def test_build_dot_structure():
    root_id, child_id, trace = _build_trace()
    dot = build_dot(trace)
    # valid-ish digraph
    assert dot.startswith("digraph causal {") and dot.rstrip().endswith("}")
    # subtree edge present
    assert f'"{root_id}" -> "{child_id}"' in dot
    # failed child rendered red
    assert _FAILED_FILL in dot
    # ancestor breadcrumb dashed-links into the traced root
    assert f'-> "{root_id}" [style=dashed]' in dot


if __name__ == "__main__":
    test_failed_node_is_red()
    test_build_dot_structure()
    print("render unit tests PASSED")
