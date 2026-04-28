"""Quote validation helpers."""

from __future__ import annotations


def quote_exists_in_text(quote: str, text: str) -> bool:
    return quote in text
