"""Simple retry helper for future LLM calls."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def retry(operation: Callable[[], T], *, attempts: int = 3) -> T:
    last_error: Exception | None = None
    for _ in range(max(1, attempts)):
        try:
            return operation()
        except Exception as exc:  # pragma: no cover - exercised by future LLM integration
            last_error = exc
    if last_error is None:  # pragma: no cover
        raise RuntimeError("Retry failed without an exception.")
    raise last_error
