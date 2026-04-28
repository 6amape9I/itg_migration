"""Snippet store placeholder."""

from __future__ import annotations

from pathlib import Path

from itg_kb.io.jsonl import write_jsonl


def write_snippets(path: Path, snippets: list[dict[str, object]]) -> None:
    write_jsonl(path, snippets)
