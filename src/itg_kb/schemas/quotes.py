"""Quote artifact schema."""

from __future__ import annotations

from pydantic import BaseModel


class QuoteRecord(BaseModel):
    quote_id: str
    tag_id: str
    doc_id: str
    block_id: str
    question: str
    answer_quote: str
    char_start: int
    char_end: int
    confidence: float
