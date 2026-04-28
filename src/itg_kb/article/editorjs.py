"""Editor.js rendering placeholder."""

from __future__ import annotations


def markdown_to_editorjs(markdown: str) -> dict[str, object]:
    return {
        "time": None,
        "blocks": [{"type": "paragraph", "data": {"text": markdown}}],
        "version": "2.30",
    }
