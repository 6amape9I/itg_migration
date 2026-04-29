"""Block-level document schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DocumentBlock(BaseModel):
    block_id: str
    doc_id: str
    order: int
    type: str
    text: str
    html: str | None = None
    level: int | None = None
    parent_path: list[str] = Field(default_factory=list)
    heading_path: list[str] = Field(default_factory=list)
    dom_path: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    text_hash: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
