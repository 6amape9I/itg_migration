"""Small text helpers for deterministic tagging."""

from __future__ import annotations

import json
import math
import re
from typing import Any


def safe_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value)


def safe_int(value: Any, *, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, float) and math.isnan(value):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_surface(value: str) -> str:
    normalized = normalize_spaces(value).lower().replace("ё", "е")
    normalized = re.sub(r"^[\W_]+|[\W_]+$", "", normalized, flags=re.UNICODE)
    normalized = re.sub(r"\s*([:;,.])\s*", r"\1 ", normalized)
    return normalize_spaces(normalized)


def strip_list_marker(value: str) -> str:
    return normalize_spaces(re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", value))


def decode_json_value(value: Any) -> Any:
    if value is None:
        return value
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("{", "[")):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                return value
    return value


def ensure_string_list(value: Any) -> list[str]:
    decoded = decode_json_value(value)
    if isinstance(decoded, list):
        return [safe_text(item) for item in decoded if safe_text(item)]
    text = safe_text(decoded)
    return [text] if text else []
