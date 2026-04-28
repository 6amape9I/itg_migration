"""Stable artifact identifiers."""

from __future__ import annotations

import re

from itg_kb.core.hashing import stable_hash


def make_doc_id(*, source_id: str | None, name: str, content_hash_value: str) -> str:
    source = source_id.strip() if source_id else name.strip()
    return f"doc_{stable_hash(source + content_hash_value, length=20)}"


def make_block_id(*, doc_id: str, order: int, block_text: str) -> str:
    return f"blk_{stable_hash(f'{doc_id}:{order}:{block_text}', length=20)}"


def slugify(value: str, *, fallback: str = "item") -> str:
    lowered = value.lower()
    slug = re.sub(r"[^0-9a-zа-яё]+", "-", lowered, flags=re.IGNORECASE).strip("-")
    return slug or fallback
