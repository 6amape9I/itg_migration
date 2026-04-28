"""LLM client protocol."""

from __future__ import annotations

from typing import Protocol


class LLMClient(Protocol):
    def generate_json(
        self,
        *,
        messages: list[dict[str, object]],
        schema: dict[str, object],
        model_profile: str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        timeout_s: int = 120,
    ) -> dict[str, object]:
        """Generate JSON validated by the caller against a schema."""
