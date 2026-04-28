"""SGLang adapter placeholder.

The bootstrap project does not import or install SGLang.
"""

from __future__ import annotations

from itg_kb.llm.openai_compatible import OpenAICompatibleClient


def make_sglang_client(
    *, base_url: str, api_key: str | None = None, model: str | None = None
) -> OpenAICompatibleClient:
    return OpenAICompatibleClient(base_url=base_url, api_key=api_key, model=model)
