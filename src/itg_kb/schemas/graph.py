"""Knowledge graph schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    node_id: str
    name: str
    type: str
    aliases: list[str] = Field(default_factory=list)
    source_tag_id: str | None = None
    confidence: float = 0.0


class GraphEdge(BaseModel):
    edge_id: str
    source_node_id: str
    target_node_id: str
    relation_type: str
    weight: float
    evidence_ids: list[str] = Field(default_factory=list)


class GraphArtifact(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
