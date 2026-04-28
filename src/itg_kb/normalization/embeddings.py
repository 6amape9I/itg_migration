"""Embedding placeholder.

Embedding models are intentionally not installed during bootstrap.
"""

from __future__ import annotations


def embed_texts(_texts: list[str]) -> list[list[float]]:
    raise RuntimeError("Embedding backend is not configured.")
