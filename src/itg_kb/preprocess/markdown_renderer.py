"""Markdown rendering helpers."""

from __future__ import annotations

from markdownify import markdownify

from itg_kb.preprocess.html_cleaner import has_html_markup, normalize_whitespace
from itg_kb.schemas.blocks import DocumentBlock


def render_markdown(raw_content: str) -> str:
    if has_html_markup(raw_content):
        return normalize_whitespace(markdownify(raw_content or "", heading_style="ATX"))
    return normalize_whitespace(raw_content or "")


def render_blocks_markdown(blocks: list[DocumentBlock]) -> str:
    rendered: list[str] = []
    for block in blocks:
        if block.type == "heading":
            level = block.level or 2
            rendered.append(f"{'#' * max(1, min(level, 6))} {block.text}")
        elif block.type == "list_item":
            rendered.append(f"- {block.text}")
        elif block.type == "blockquote":
            rendered.append(f"> {block.text}")
        elif block.type == "table":
            rendered.append(block.text)
        else:
            rendered.append(block.text)
    return "\n\n".join(rendered).strip()
