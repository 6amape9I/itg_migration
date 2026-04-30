"""Tagging and tag catalog schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TopicUnit(BaseModel):
    topic_unit_id: str
    doc_id: str
    unit_index: int
    unit_type: str
    title: str | None = None
    heading_path: list[str] = Field(default_factory=list)
    block_ids: list[str] = Field(default_factory=list)
    text: str
    text_length: int
    char_start: int | None = None
    char_end: int | None = None
    source_block_types: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class TagCandidate(BaseModel):
    candidate_id: str
    doc_id: str
    topic_unit_id: str | None = None

    role: str
    surface: str
    normalized_surface: str
    core_surface: str | None = None
    normalized_core_surface: str | None = None

    entity_type: str
    entity_subtype: str | None = None
    facet_type: str | None = None
    facets: list[str] = Field(default_factory=list)
    qualifiers: dict[str, str] = Field(default_factory=dict)

    sources: list[str] = Field(default_factory=list)
    evidence_block_ids: list[str] = Field(default_factory=list)
    evidence_texts: list[str] = Field(default_factory=list)
    heading_paths: list[list[str]] = Field(default_factory=list)

    score: float
    score_components: dict[str, float] = Field(default_factory=dict)
    confidence_bucket: str

    needs_review: bool = False
    review_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CandidateEvidence(BaseModel):
    evidence_id: str
    candidate_id: str
    doc_id: str
    topic_unit_id: str | None = None
    block_id: str
    evidence_type: str
    text: str
    heading_path: list[str] = Field(default_factory=list)
    char_start: int | None = None
    char_end: int | None = None
    weight: float


class DocTopicSummary(BaseModel):
    doc_id: str
    title: str
    normalization_status: str
    topic_unit_count: int
    candidate_count_total: int
    primary_candidate_ids: list[str] = Field(default_factory=list)
    top_candidate_ids_for_review: list[str] = Field(default_factory=list)
    facet_only_count: int = 0
    cross_topic_reference_count: int = 0
    needs_review: bool = False
    review_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)


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
