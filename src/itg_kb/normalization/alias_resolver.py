"""Curation alias resolver placeholder."""

from __future__ import annotations


def resolve_alias(surface: str, aliases: dict[str, str] | None = None) -> str:
    return (aliases or {}).get(surface, surface)
