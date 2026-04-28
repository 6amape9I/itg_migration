"""OpenAI-compatible lazy client."""

from __future__ import annotations

from typing import Any


class OpenAICompatibleClient:
    def __init__(
        self, *, base_url: str, api_key: str | None = None, model: str | None = None
    ) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.model = model

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
        client = self._client(timeout_s)
        model = self.model or model_profile
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "response", "schema": schema, "strict": True},
            },
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("LLM returned empty content.")
        import json

        return json.loads(content)

    def _client(self, timeout_s: int) -> Any:
        try:
            from openai import OpenAI
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "OpenAI-compatible calls require optional dependency 'openai'. "
                "Install it only when an LLM backend is configured."
            ) from exc
        return OpenAI(base_url=self.base_url, api_key=self.api_key or "EMPTY", timeout=timeout_s)
