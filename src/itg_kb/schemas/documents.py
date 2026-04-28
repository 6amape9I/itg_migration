"""Document-level artifact schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DocumentRecord(BaseModel):
    doc_id: str
    source_id: str | None = None
    source_row: int
    name: str
    description: str | None = None
    raw_content: str
    content_hash: str
    raw_length: int
    has_html: bool
    ingest_status: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class NormalizedDocument(BaseModel):
    doc_id: str
    title: str
    content_hash: str
    plain_text: str
    markdown: str
    block_count: int
    normalization_status: str
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
