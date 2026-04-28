"""Tagging and tag catalog schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TagCandidate(BaseModel):
    candidate_id: str
    doc_id: str
    surface: str
    normalized_surface: str
    entity_type: str | None = None
    sources: list[str] = Field(default_factory=list)
    evidence_block_ids: list[str] = Field(default_factory=list)
    evidence_texts: list[str] = Field(default_factory=list)
    score: float = 0.0
    score_components: dict[str, float] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TagRecord(BaseModel):
    tag_id: str
    canonical_name: str
    entity_type: str
    aliases: list[str] = Field(default_factory=list)
    status: str
    doc_count: int = 0
    confidence: float = 0.0
    created_from_candidates: list[str] = Field(default_factory=list)


class TagDocLink(BaseModel):
    tag_id: str
    doc_id: str
    candidate_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    evidence_block_ids: list[str] = Field(default_factory=list)
