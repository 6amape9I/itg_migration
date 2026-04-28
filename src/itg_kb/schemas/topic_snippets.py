"""Topic corpus snippet schema."""

from __future__ import annotations

from pydantic import BaseModel


class TopicSnippet(BaseModel):
    snippet_id: str
    tag_id: str
    doc_id: str
    block_id: str
    text: str
    relevance: float
    extraction_method: str
    quote_candidate: bool = False
