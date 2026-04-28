"""Checkpoint and artifact validation helpers."""

from __future__ import annotations

from pathlib import Path


def existing_outputs(paths: list[Path]) -> dict[str, bool]:
    return {str(path): path.exists() for path in paths}


def missing_outputs(paths: list[Path]) -> list[str]:
    return [str(path) for path in paths if not path.exists()]
