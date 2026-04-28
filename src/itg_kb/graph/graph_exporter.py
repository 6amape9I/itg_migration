"""Graph export placeholder."""

from __future__ import annotations


def export_graph(
    nodes: list[dict[str, object]], edges: list[dict[str, object]]
) -> dict[str, object]:
    return {"nodes": nodes, "edges": edges}
