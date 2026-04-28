"""Placeholder for a future Docling adapter.

Docling is intentionally not a dependency in the bootstrap pass.
"""

from __future__ import annotations


class DoclingAdapter:
    def convert(self, *_args: object, **_kwargs: object) -> None:
        raise RuntimeError("Docling support is not installed in the bootstrap project.")
