"""Sampling helpers for review."""

from __future__ import annotations


def take_sample(items: list[object], limit: int = 20) -> list[object]:
    return items[:limit]
