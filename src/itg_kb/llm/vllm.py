"""vLLM adapter placeholder.

The project targets vLLM through an OpenAI-compatible endpoint, so no vLLM package is imported here.
"""

from __future__ import annotations

from itg_kb.llm.openai_compatible import OpenAICompatibleClient


def make_vllm_client(
    *, base_url: str, api_key: str | None = None, model: str | None = None
) -> OpenAICompatibleClient:
    return OpenAICompatibleClient(base_url=base_url, api_key=api_key, model=model)
