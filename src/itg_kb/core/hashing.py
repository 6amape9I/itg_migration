"""Stable hashing helpers."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


def normalize_text_for_hash(value: str | None) -> str:
    """Normalize technical line-ending differences before hashing raw content."""
    if value is None:
        return ""
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"[ \t]+\n", "\n", normalized).strip()


def stable_hash(value: str | bytes | dict[str, Any] | list[Any], *, length: int = 16) -> str:
    """Return a deterministic short SHA-256 hash."""
    if isinstance(value, bytes):
        payload = value
    elif isinstance(value, str):
        payload = value.encode("utf-8")
    else:
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:length]


def content_hash(raw_content: str | None) -> str:
    return stable_hash(normalize_text_for_hash(raw_content), length=24)
