from collections.abc import Awaitable, Callable
from itertools import pairwise
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph


class WorkflowData(TypedDict, total=False):
    context: Any
    message: str
    command: Any
    state: Any
    reply: Any
    prepared: Any
    preview: Any
    expected_version: int
    confirmed: bool


Node = Callable[[WorkflowData], Awaitable[dict[str, Any]]]


def build_workflow(nodes: dict[str, Node]):
    """Compile an acyclic, fixed-length workflow; nodes skip when a reply is terminal."""
    graph = StateGraph(WorkflowData)
    ordered = (
        "precheck",
        "interpret",
        "reduce_resolve",
        "validate",
        "query_integrations",
        "preview",
        "confirm",
        "execute",
    )
    for name in ordered:
        graph.add_node(name, nodes[name])
    graph.add_edge(START, ordered[0])
    for current, following in pairwise(ordered):
        graph.add_edge(current, following)
    graph.add_edge(ordered[-1], END)
    return graph.compile()
