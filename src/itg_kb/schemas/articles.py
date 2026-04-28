"""Article artifact schema."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ArticleArtifact(BaseModel):
    tag_id: str
    canonical_name: str
    markdown: str
    editorjs: dict[str, Any] = Field(default_factory=dict)
    source_snippet_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
